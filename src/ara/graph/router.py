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
