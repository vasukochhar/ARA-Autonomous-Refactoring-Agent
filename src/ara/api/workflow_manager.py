"""
Workflow Manager - Manage long-running refactoring workflows.

Provides utilities for starting, pausing, resuming, and querying workflows.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import uuid

import structlog

from ara.state.schema import create_initial_state, AgentState
from ara.state.models import FileContext, ApprovalStatus
from ara.graph.builder import create_graph
from ara.persistence import get_langgraph_checkpointer

logger = structlog.get_logger()


@dataclass
class WorkflowInfo:
    """Information about a workflow."""
    
    workflow_id: str
    thread_id: str
    refactoring_goal: str
    status: str
    created_at: datetime
    updated_at: datetime
    current_file: Optional[str] = None
    iteration_count: int = 0
    error_message: Optional[str] = None


class WorkflowManager:
    """
    Manages ARA workflows with persistence support.
    
    Handles workflow lifecycle: creation, execution, pause, resume, and status.
    """
    
    def __init__(self, use_persistence: bool = True):
        """
        Initialize the workflow manager.
        
        Args:
            use_persistence: Whether to use PostgreSQL persistence
        """
        self.use_persistence = use_persistence
        self._checkpointer = None
        self._graph = None
        self._workflows: Dict[str, WorkflowInfo] = {}
    
    async def _get_checkpointer(self):
        """Get or create the checkpointer."""
        if self._checkpointer is None and self.use_persistence:
            self._checkpointer = await get_langgraph_checkpointer()
        return self._checkpointer
    
    async def _get_graph(self):
        """Get or create the graph."""
        if self._graph is None:
            checkpointer = await self._get_checkpointer()
            self._graph = create_graph(with_checkpointer=checkpointer)
        return self._graph
    
    async def start_workflow(
        self,
        refactoring_goal: str,
        files: Dict[str, str],
        max_iterations: int = 3,
        workflow_id: Optional[str] = None,
    ) -> WorkflowInfo:
        """
        Start a new refactoring workflow.
        
        Args:
            refactoring_goal: What to refactor
            files: Dict mapping filepath to source code
            max_iterations: Maximum self-correction iterations
            workflow_id: Optional custom workflow ID
        
        Returns:
            WorkflowInfo with the new workflow details
        """
        workflow_id = workflow_id or str(uuid.uuid4())
        thread_id = f"thread_{workflow_id}"
        
        logger.info(
            "starting_workflow",
            workflow_id=workflow_id,
            goal=refactoring_goal,
            files=len(files),
        )
        
        # Create initial state
        state = create_initial_state(
            refactoring_goal=refactoring_goal,
            max_iterations=max_iterations,
            workflow_id=workflow_id,
        )
        
        # Add files to state
        file_contexts = {}
        for filepath, content in files.items():
            file_contexts[filepath] = FileContext(
                filepath=filepath,
                original_content=content,
            )
        state["files"] = file_contexts
        
        # Create workflow info
        now = datetime.now()
        info = WorkflowInfo(
            workflow_id=workflow_id,
            thread_id=thread_id,
            refactoring_goal=refactoring_goal,
            status="RUNNING",
            created_at=now,
            updated_at=now,
        )
        self._workflows[workflow_id] = info
        
        # Start the graph execution
        graph = await self._get_graph()
        
        try:
            config = {"configurable": {"thread_id": thread_id}}
            result = await graph.ainvoke(state, config)
            
            # Update workflow info
            if result.get("error_state"):
                info.status = "ERROR"
                info.error_message = result.get("error_state")
            else:
                info.status = "COMPLETED" if result.get("approval_status") == "APPROVED" else "AWAITING_REVIEW"
            info.current_file = result.get("current_file_path")
            info.iteration_count = result.get("iteration_count", 0)
            info.updated_at = datetime.now()
            
            logger.info("workflow_completed", workflow_id=workflow_id, status=info.status)
            
        except Exception as e:
            # Check if it's an interrupt (expected for human review)
            if "interrupt" in str(e).lower():
                info.status = "AWAITING_REVIEW"
                logger.info("workflow_interrupted", workflow_id=workflow_id)
            else:
                info.status = "ERROR"
                info.error_message = str(e)
                logger.error("workflow_error", workflow_id=workflow_id, error=str(e))
        
        return info
    
    async def resume_workflow(
        self,
        workflow_id: str,
        action: str,
        feedback: Optional[str] = None,
    ) -> WorkflowInfo:
        """
        Resume a paused workflow with human input.
        
        Args:
            workflow_id: ID of the workflow to resume
            action: Action to take (APPROVE, REJECT, MODIFY)
            feedback: Optional feedback from the human
        
        Returns:
            Updated WorkflowInfo
        """
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        info = self._workflows[workflow_id]
        
        logger.info(
            "resuming_workflow",
            workflow_id=workflow_id,
            action=action,
        )
        
        graph = await self._get_graph()
        config = {"configurable": {"thread_id": info.thread_id}}
        
        # Resume with the human response
        human_response = {
            "action": action,
            "feedback": feedback or "",
        }
        
        try:
            result = await graph.ainvoke(None, config, interrupt_response=human_response)
            
            info.status = "COMPLETED" if result.get("approval_status") == "APPROVED" else "AWAITING_REVIEW"
            info.updated_at = datetime.now()
            
        except Exception as e:
            if "interrupt" in str(e).lower():
                info.status = "AWAITING_REVIEW"
            else:
                info.status = "ERROR"
                info.error_message = str(e)
        
        return info
    
    async def get_workflow_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the current state of a workflow from the graph.
        
        Args:
            workflow_id: ID of the workflow
            
        Returns:
            Dictionary containing the current state, or None if not found
        """
        if workflow_id not in self._workflows:
            return None
            
        info = self._workflows[workflow_id]
        
        # Get the graph and checkpointer
        checkpointer = await self._get_checkpointer()
        graph = await self._get_graph()
        
        # Get state from checkpointer
        config = {"configurable": {"thread_id": info.thread_id}}
        
        try:
            # Retrieve the latest state snapshot
            snapshot = await graph.aget_state(config)
            return snapshot.values
        except Exception as e:
            logger.error("get_state_error", workflow_id=workflow_id, error=str(e))
            return None
            
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowInfo]:
        """Get workflow information by ID."""
        return self._workflows.get(workflow_id)
    
    def list_workflows(self, status: Optional[str] = None) -> List[WorkflowInfo]:
        """
        List all workflows, optionally filtered by status.
        
        Args:
            status: Optional status filter
        
        Returns:
            List of WorkflowInfo objects
        """
        workflows = list(self._workflows.values())
        
        if status:
            workflows = [w for w in workflows if w.status == status]
        
        return sorted(workflows, key=lambda w: w.updated_at, reverse=True)
    
    async def list_checkpoints(self, workflow_id: str) -> list:
        """
        List all checkpoints for a workflow (for time-travel debugging).
        
        Args:
            workflow_id: The workflow ID
        
        Returns:
            List of checkpoint metadata dicts
        """
        try:
            from ara.persistence.database import get_async_connection_context, CheckpointRepository
            
            async with get_async_connection_context() as conn:
                repo = CheckpointRepository(conn)
                checkpoints = await repo.list_checkpoints(workflow_id)
                return checkpoints
        except Exception as e:
            logger.warning("list_checkpoints_failed", error=str(e))
            return []
    
    async def rewind_to_checkpoint(
        self, workflow_id: str, step_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        Rewind a workflow to a specific checkpoint (time-travel debugging).
        
        This restores the workflow state to a previous step, allowing
        engineers to inspect or modify the state before resuming.
        
        Args:
            workflow_id: The workflow ID
            step_number: Step number to rewind to
        
        Returns:
            The restored state or None if not found
        """
        try:
            from ara.persistence.database import get_async_connection_context, CheckpointRepository
            
            async with get_async_connection_context() as conn:
                repo = CheckpointRepository(conn)
                
                # Get the state at that step
                state = await repo.rewind_to_step(workflow_id, step_number)
                
                if state:
                    # Delete checkpoints after this step
                    await repo.delete_after_step(workflow_id, step_number)
                    
                    # Update workflow info
                    if workflow_id in self._workflows:
                        self._workflows[workflow_id].status = "REWOUND"
                        self._workflows[workflow_id].updated_at = datetime.now()
                    
                    logger.info("workflow_rewound", workflow_id=workflow_id, step=step_number)
                    return state
                
                return None
        except Exception as e:
            logger.error("rewind_to_checkpoint_failed", error=str(e))
            return None
    
    async def save_checkpoint(
        self, workflow_id: str, step_number: int, node_name: str, state: dict
    ) -> bool:
        """
        Save a checkpoint of the current workflow state.
        
        Called automatically after each node execution for time-travel support.
        
        Args:
            workflow_id: The workflow ID
            step_number: Current step number
            node_name: Name of the node that just executed
            state: Current workflow state
        
        Returns:
            True if saved successfully
        """
        try:
            from ara.persistence.database import get_async_connection_context, CheckpointRepository
            
            checkpoint_id = f"{workflow_id}_step_{step_number}"
            
            async with get_async_connection_context() as conn:
                repo = CheckpointRepository(conn)
                await repo.save_checkpoint(
                    workflow_id=workflow_id,
                    checkpoint_id=checkpoint_id,
                    step_number=step_number,
                    node_name=node_name,
                    state=state,
                )
            return True
        except Exception as e:
            logger.warning("save_checkpoint_failed", error=str(e))
            return False


# Global workflow manager instance
_workflow_manager: Optional[WorkflowManager] = None


def get_workflow_manager() -> WorkflowManager:
    """Get the global workflow manager instance."""
    global _workflow_manager
    if _workflow_manager is None:
        _workflow_manager = WorkflowManager()
    return _workflow_manager
