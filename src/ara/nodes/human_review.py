"""
Human Review Node - Human-in-the-Loop approval workflow.

Implements interrupt functionality for human review and approval of changes.
"""

from enum import Enum
from typing import Optional

import structlog
from langgraph.types import interrupt

from ara.state.schema import AgentState
from ara.state.models import ApprovalStatus, FileContext, FileStatus

logger = structlog.get_logger()


class ReviewAction(str, Enum):
    """Possible actions from human review."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    MODIFY = "MODIFY"
    SKIP = "SKIP"


def human_review_node(state: AgentState) -> dict:
    """
    Human review interrupt node.

    This node pauses the workflow and waits for human input.
    The workflow can be resumed with feedback.

    Args:
        state: Current agent state

    Returns:
        Updated state with approval status
    """
    current_file = state.get("current_file_path")
    files = state.get("files", {})

    logger.info("human_review_start", file=current_file)

    # Get file context for review
    file_ctx = files.get(current_file) if current_file else None
    diff = None

    if file_ctx:
        if isinstance(file_ctx, FileContext):
            diff = file_ctx.diff
        else:
            diff = file_ctx.get("diff")

    # Create review request
    review_request = {
        "file": current_file,
        "diff": diff,
        "message": "Please review the proposed changes and approve or reject.",
    }

    # Interrupt and wait for human input
    # This will pause the graph and wait for resume
    human_response = interrupt(review_request)

    # Process the response
    if human_response:
        action = human_response.get("action", ReviewAction.REJECT.value)
        feedback = human_response.get("feedback", "")

        logger.info("human_response_received", action=action)

        if action == ReviewAction.APPROVE.value:
            return {
                "approval_status": ApprovalStatus.APPROVED.value,
                "human_feedback": feedback,
            }
        elif action == ReviewAction.MODIFY.value:
            return {
                "approval_status": ApprovalStatus.PENDING.value,
                "human_feedback": feedback,
                # Trigger regeneration with feedback
            }
        else:
            return {
                "approval_status": ApprovalStatus.REJECTED.value,
                "human_feedback": feedback,
            }

    return {"approval_status": ApprovalStatus.PENDING.value}


def committer_node(state: AgentState) -> dict:
    """
    Committer node - Applies approved changes.

    This node writes the approved changes to disk and can
    optionally create a git commit or PR.

    Args:
        state: Current agent state

    Returns:
        Updated state with commit information
    """
    approval_status = state.get("approval_status")
    current_file = state.get("current_file_path")
    files = state.get("files", {})

    logger.info("committer_start", file=current_file, status=approval_status)

    if approval_status != ApprovalStatus.APPROVED.value:
        logger.warning("committer_not_approved", status=approval_status)
        return {"error_state": "Cannot commit: changes not approved"}

    if not current_file or current_file not in files:
        return {"error_state": "No file to commit"}

    file_ctx = files[current_file]
    
    # Get the modified content
    if isinstance(file_ctx, FileContext):
        modified_content = file_ctx.modified_content
    else:
        modified_content = file_ctx.get("modified_content")

    if not modified_content:
        return {"error_state": "No modified content to commit"}

    try:
        # Write the file
        from ara.tools.file_ops import write_file
        
        write_file.invoke({
            "filepath": current_file,
            "content": modified_content,
        })

        logger.info("file_committed", file=current_file)

        # Update file status
        updated_files = dict(files)
        if isinstance(file_ctx, FileContext):
            updated_files[current_file] = FileContext(
                filepath=file_ctx.filepath,
                original_content=file_ctx.original_content,
                modified_content=file_ctx.modified_content,
                diff=file_ctx.diff,
                status=FileStatus.COMPLETED,
            )
        else:
            file_ctx["status"] = FileStatus.COMPLETED.value
            updated_files[current_file] = file_ctx

        return {
            "files": updated_files,
            "human_feedback": f"Successfully committed changes to {current_file}",
        }

    except Exception as e:
        logger.error("commit_error", error=str(e))
        return {"error_state": f"Commit failed: {str(e)}"}


def create_backup_before_commit(filepath: str) -> Optional[str]:
    """
    Create a backup of a file before committing changes.

    Args:
        filepath: Path to the file

    Returns:
        Path to the backup file, or None on error
    """
    try:
        from ara.tools.file_ops import create_backup
        
        result = create_backup.invoke({"filepath": filepath})
        return result
    except Exception as e:
        logger.warning("backup_failed", filepath=filepath, error=str(e))
        return None
