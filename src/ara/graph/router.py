"""
Graph Router - Conditional routing logic for the ARA workflow.

Implements the self-correction loop routing based on validation results.
"""

import structlog

from ara.state.schema import AgentState
from ara.state.models import ValidationResult

logger = structlog.get_logger()


def route_after_validation(state: AgentState) -> str:
    """
    Determine the next node after validation.

    Routing logic:
    1. If validation passed -> go to human_review (or end for now)
    2. If validation failed and retries remain -> go to reflector
    3. If max retries reached -> escalate/end

    Args:
        state: Current agent state

    Returns:
        Next node name: "success", "reflect", or "escalate"
    """
    validation_history = state.get("validation_history", [])
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 3)

    # Check if latest validation passed
    if validation_history:
        # Get only ValidationResult objects from recent history
        recent_results = [
            v for v in validation_history[-5:]
            if isinstance(v, ValidationResult)
        ]

        if recent_results:
            # Check if all recent validations passed
            all_passed = all(r.passed for r in recent_results)

            if all_passed:
                logger.info("routing_to_success", iteration=iteration_count)
                return "success"
        else:
            # No validation results, treat as failure
            pass

    # Check if we have retries left
    if iteration_count < max_iterations:
        logger.info(
            "routing_to_reflect",
            iteration=iteration_count,
            max_iterations=max_iterations,
        )
        return "reflect"

    # Max retries reached
    logger.warning(
        "routing_to_escalate",
        iteration=iteration_count,
        max_iterations=max_iterations,
    )
    return "escalate"


def should_continue_analysis(state: AgentState) -> str:
    """
    Determine if there are more files to process after current file completes.

    Args:
        state: Current agent state

    Returns:
        "continue" if more files, "done" if all processed
    """
    files = state.get("files", {})
    current_file = state.get("current_file_path")

    # Count files that haven't been processed yet
    pending_files = [
        f for f, ctx in files.items()
        if f != current_file and ctx.get("status") == "PENDING"
    ]

    if pending_files:
        logger.info("more_files_to_process", count=len(pending_files))
        return "continue"

    logger.info("all_files_processed")
    return "done"


def check_for_errors(state: AgentState) -> str:
    """
    Check if there are any error states that should halt processing.

    Args:
        state: Current agent state

    Returns:
        "error" if error state exists, "continue" otherwise
    """
    error_state = state.get("error_state")

    if error_state:
        logger.error("error_state_detected", error=error_state)
        return "error"

    return "continue"


def route_next_file(state: AgentState) -> dict:
    """
    Advance to the next file in the processing queue.

    Called after a file is successfully processed. Updates current_file_path
    to the next file in the queue.

    Args:
        state: Current agent state

    Returns:
        State update with next file, or None if queue exhausted
    """
    file_queue = state.get("file_queue", [])
    current_index = state.get("file_queue_index", 0)
    
    next_index = current_index + 1
    
    if next_index < len(file_queue):
        next_file = file_queue[next_index]
        logger.info("advancing_to_next_file", 
                    index=next_index, 
                    total=len(file_queue), 
                    file=next_file)
        return {
            "current_file_path": next_file,
            "file_queue_index": next_index,
            "iteration_count": 0,  # Reset iterations for new file
        }
    
    logger.info("file_queue_exhausted", total_processed=len(file_queue))
    return {
        "file_queue_index": next_index,
    }


def has_more_files(state: AgentState) -> str:
    """
    Check if there are more files to process in the queue.

    Args:
        state: Current agent state

    Returns:
        "next_file" if more files, "done" if queue exhausted
    """
    file_queue = state.get("file_queue", [])
    current_index = state.get("file_queue_index", 0)
    
    if current_index + 1 < len(file_queue):
        logger.info("more_files_in_queue", 
                    remaining=len(file_queue) - current_index - 1)
        return "next_file"
    
    logger.info("all_files_complete", total=len(file_queue))
    return "done"


def check_cycle_detection(state: AgentState) -> str:
    """
    Check for code oscillation (cycle detection).

    If the same code hash appears twice, we're oscillating and should stop.

    Args:
        state: Current agent state

    Returns:
        "cycle" if oscillation detected, "continue" otherwise
    """
    import hashlib
    
    code_hashes = state.get("code_hashes", [])
    generated_code = state.get("generated_code_snippet", "")
    
    if not generated_code:
        return "continue"
    
    # Compute hash of generated code
    code_hash = hashlib.md5(generated_code.encode()).hexdigest()
    
    if code_hash in code_hashes:
        logger.warning("code_oscillation_detected", 
                       hash=code_hash,
                       history_size=len(code_hashes))
        return "cycle"
    
    return "continue"

