"""
FastAPI Application - REST API for ARA.

Provides endpoints to start, monitor, and control refactoring workflows.
"""

from typing import Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import structlog

from ara.api.workflow_manager import get_workflow_manager, WorkflowInfo

logger = structlog.get_logger()

# Create FastAPI app
app = FastAPI(
    title="ARA - Autonomous Refactoring Agent",
    description="AI-powered code refactoring with human-in-the-loop approval",
    version="0.1.0",
)

# Add CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class StartRefactorRequest(BaseModel):
    """Request to start a refactoring workflow."""
    
    refactoring_goal: str = Field(
        ...,
        description="Description of the refactoring to perform",
        example="Add type hints to all functions",
    )
    files: Dict[str, str] = Field(
        ...,
        description="Dictionary mapping file paths to their content",
    )
    max_iterations: int = Field(
        default=3,
        description="Maximum self-correction iterations",
        ge=1,
        le=10,
    )


class WorkflowResponse(BaseModel):
    """Response containing workflow information."""
    
    workflow_id: str
    status: str
    refactoring_goal: str
    current_file: Optional[str] = None
    iteration_count: int = 0
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None


class ResumeWorkflowRequest(BaseModel):
    """Request to resume a paused workflow."""
    
    action: str = Field(
        ...,
        description="Action to take: APPROVE, REJECT, or MODIFY",
        pattern="^(APPROVE|REJECT|MODIFY)$",
    )
    feedback: Optional[str] = Field(
        default=None,
        description="Optional feedback for the refactoring agent",
    )


class SubmitFeedbackRequest(BaseModel):
    """Request to submit feedback on a workflow."""
    
    feedback: str = Field(
        ...,
        description="Feedback to incorporate into the refactoring",
    )


class WorkflowStatusResponse(BaseModel):
    """Detailed status of a workflow."""
    
    workflow_id: str
    status: str
    refactoring_goal: str
    current_file: Optional[str] = None
    iteration_count: int = 0
    files_processed: int = 0
    files_total: int = 0
    current_diff: Optional[str] = None
    refactoring_summary: Optional[str] = None
    validation_results: List[dict] = []
    error_message: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================

def _workflow_to_response(info: WorkflowInfo) -> WorkflowResponse:
    """Convert WorkflowInfo to API response."""
    return WorkflowResponse(
        workflow_id=info.workflow_id,
        status=info.status,
        refactoring_goal=info.refactoring_goal,
        current_file=info.current_file,
        iteration_count=info.iteration_count,
        created_at=info.created_at,
        updated_at=info.updated_at,
        error_message=info.error_message,
    )


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "name": "ARA - Autonomous Refactoring Agent",
        "version": "0.1.0",
        "status": "healthy",
    }


@app.post("/start_refactor", response_model=WorkflowResponse)
async def start_refactor(
    request: StartRefactorRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a new refactoring workflow.
    
    This endpoint initiates the refactoring process and returns immediately.
    The workflow runs in the background and can be monitored via /get_status.
    """
    logger.info(
        "api_start_refactor",
        goal=request.refactoring_goal,
        files=len(request.files),
    )
    
    manager = get_workflow_manager()
    
    try:
        info = await manager.start_workflow(
            refactoring_goal=request.refactoring_goal,
            files=request.files,
            max_iterations=request.max_iterations,
        )
        
        return _workflow_to_response(info)
        
    except Exception as e:
        logger.error("api_start_refactor_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_status/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_status(workflow_id: str):
    """
    Get the current status of a workflow.
    
    Returns detailed information about the workflow including
    current file, diff, and validation results.
    """
    manager = get_workflow_manager()
    info = manager.get_workflow(workflow_id)
    
    if not info:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    
    # Retrieve full state from the graph
    state = await manager.get_workflow_state(workflow_id)
    
    # Defaults
    files_processed = 0
    files_total = 0
    current_diff = None
    validation_results = []
    
    if state:
        # Extract files info
        files = state.get("files", {})
        files_total = len(files)
        files_processed = sum(1 for f in files.values() if getattr(f, "status", "") == "COMPLETED")
        
        # Extract current file info
        current_file_path = state.get("current_file_path")
        if current_file_path and current_file_path in files:
            file_ctx = files[current_file_path]
            # Handle both object and dict access (Pydantic model vs dict)
            if hasattr(file_ctx, "diff"):
                current_diff = file_ctx.diff
            elif isinstance(file_ctx, dict):
                current_diff = file_ctx.get("diff")
        
        # Fallback: if no current_diff found, check if any file has a diff
        # This handles cases where current_file_path might be missing or stale
        if not current_diff and files:
            for fpath, fctx in files.items():
                d = None
                if hasattr(fctx, "diff"):
                    d = fctx.diff
                elif isinstance(fctx, dict):
                    d = fctx.get("diff")
                
                if d:
                    current_diff = d
                    if not current_file_path: # Infer current file if missing
                        current_file_path = fpath
                        # Update info object too so generic response is correct
                        info.current_file = fpath
                    break
                    
        # Debug logging
        logger.info(
            "get_status_debug", 
            workflow_id=workflow_id, 
            diff_found=bool(current_diff),
            file=current_file_path,
            files_count=len(files)
        )
                
        # Extract validation results
        # Validation history is a list of lists of ValidationResult
        history = state.get("validation_history", [])
        if history:
            # Flatten the latest validation run results
            # The history structure depends on how the reducer works.
            # Usually strict LangGraph append reducer makes it a flat list of all results over time
            # or a list of lists if we append batches.
            # Let's assume the latest batch are the relevant ones.
            latest_results = history[-1] if isinstance(history[-1], list) else history
            
            # Convert objects to dicts for JSON serialization
            for res in (latest_results if isinstance(latest_results, list) else [latest_results]):
                if hasattr(res, "dict"):
                    validation_results.append(res.dict())
                elif isinstance(res, dict):
                    validation_results.append(res)
    
        if state.get("error_state"):
            error_msg = state.get("error_state")
            if info.error_message:
                info.error_message = f"{info.error_message}; {error_msg}"
            else:
                info.error_message = error_msg

    # Build detailed status response
    return WorkflowStatusResponse(
        workflow_id=info.workflow_id,
        status=info.status,
        refactoring_goal=info.refactoring_goal,
        current_file=info.current_file,
        iteration_count=info.iteration_count,
        files_processed=files_processed,
        files_total=files_total,
        current_diff=current_diff,
        refactoring_summary=state.get("refactoring_summary"),
        validation_results=validation_results,
        error_message=info.error_message,
    )


@app.post("/resume_workflow/{workflow_id}", response_model=WorkflowResponse)
async def resume_workflow(workflow_id: str, request: ResumeWorkflowRequest):
    """
    Resume a paused workflow with human input.
    
    Used when the workflow is awaiting human review to approve,
    reject, or modify the proposed changes.
    """
    logger.info(
        "api_resume_workflow",
        workflow_id=workflow_id,
        action=request.action,
    )
    
    manager = get_workflow_manager()
    
    try:
        info = await manager.resume_workflow(
            workflow_id=workflow_id,
            action=request.action,
            feedback=request.feedback,
        )
        
        return _workflow_to_response(info)
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("api_resume_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/submit_feedback/{workflow_id}", response_model=WorkflowResponse)
async def submit_feedback(workflow_id: str, request: SubmitFeedbackRequest):
    """
    Submit feedback to modify a workflow's behavior.
    
    This is used to provide guidance to the refactoring agent
    without approving or rejecting the current changes.
    """
    manager = get_workflow_manager()
    
    try:
        info = await manager.resume_workflow(
            workflow_id=workflow_id,
            action="MODIFY",
            feedback=request.feedback,
        )
        
        return _workflow_to_response(info)
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflows", response_model=List[WorkflowResponse])
async def list_workflows(status: Optional[str] = None):
    """
    List all workflows, optionally filtered by status.
    
    Status can be: RUNNING, AWAITING_REVIEW, COMPLETED, ERROR
    """
    manager = get_workflow_manager()
    workflows = manager.list_workflows(status=status)
    
    return [_workflow_to_response(w) for w in workflows]


@app.delete("/workflows/{workflow_id}")
async def cancel_workflow(workflow_id: str):
    """
    Cancel a running workflow.
    
    Note: This does not undo any changes already made.
    """
    manager = get_workflow_manager()
    info = manager.get_workflow(workflow_id)
    
    if not info:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    
    # Mark as cancelled
    info.status = "CANCELLED"
    info.updated_at = datetime.now()
    
    return {"message": f"Workflow {workflow_id} cancelled"}


# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    logger.info("ara_api_starting")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown."""
    logger.info("ara_api_shutting_down")
