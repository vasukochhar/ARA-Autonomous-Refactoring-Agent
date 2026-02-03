"""
Graph Builder - LangGraph StateGraph construction for ARA.

Builds the complete refactoring agent graph with all nodes and edges.
"""

import structlog
from langgraph.graph import StateGraph, END

from ara.state.schema import AgentState
from ara.nodes.analyzer import analyzer_node
from ara.nodes.generator import generator_node
from ara.nodes.validator import validator_node
from ara.nodes.reflector import reflector_node
from ara.graph.router import route_after_validation

logger = structlog.get_logger()


def create_graph(with_checkpointer=None) -> StateGraph:
    """
    Create the ARA LangGraph StateGraph.

    The graph implements the following flow:
    
    START -> analyzer -> generator -> validator -> [routing]
                                                      |
                         +-----------+----------------+
                         |           |                |
                         v           v                v
                      success    reflector        escalate
                         |           |                |
                         v           v                v
                        END      generator           END

    Args:
        with_checkpointer: Optional checkpointer for persistence

    Returns:
        Compiled LangGraph application
    """
    logger.info("creating_graph")

    # Create the graph with AgentState
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("analyzer", analyzer_node)
    graph.add_node("generator", generator_node)
    graph.add_node("validator", validator_node)
    graph.add_node("reflector", reflector_node)

    # Success handler (placeholder for human review)
    graph.add_node("success_handler", _success_handler)

    # Escalation handler
    graph.add_node("escalate_handler", _escalate_handler)

    # Set entry point
    graph.set_entry_point("analyzer")

    # Add edges
    # analyzer -> generator
    graph.add_edge("analyzer", "generator")

    # generator -> validator
    graph.add_edge("generator", "validator")

    # validator -> conditional routing
    graph.add_conditional_edges(
        "validator",
        route_after_validation,
        {
            "success": "success_handler",
            "reflect": "reflector",
            "escalate": "escalate_handler",
        }
    )

    # reflector -> generator (retry loop)
    graph.add_edge("reflector", "generator")

    # Terminal nodes
    graph.add_edge("success_handler", END)
    graph.add_edge("escalate_handler", END)

    # Compile the graph
    if with_checkpointer:
        compiled = graph.compile(checkpointer=with_checkpointer)
    else:
        compiled = graph.compile()

    logger.info("graph_created")
    return compiled


def _success_handler(state: AgentState) -> dict:
    """
    Handle successful validation.

    This is a placeholder for the human review node in Phase 4.
    For now, it just marks the process as complete.

    Args:
        state: Current agent state

    Returns:
        Updated state with completion status
    """
    current_file = state.get("current_file_path")
    files = state.get("files", {})

    logger.info("success_handler", file=current_file)

    # Update file status to completed
    if current_file and current_file in files:
        updated_files = dict(files)
        file_ctx = updated_files[current_file]
        
        if hasattr(file_ctx, 'status'):
            # It's a FileContext object
            from ara.state.models import FileContext, FileStatus
            updated_files[current_file] = FileContext(
                filepath=file_ctx.filepath,
                original_content=file_ctx.original_content,
                modified_content=file_ctx.modified_content,
                diff=file_ctx.diff,
                status=FileStatus.COMPLETED,
            )
        else:
            # It's a dict
            file_ctx["status"] = "COMPLETED"
            updated_files[current_file] = file_ctx

        return {
            "files": updated_files,
            "approval_status": "PENDING",  # Ready for human review
        }

    return {"approval_status": "PENDING"}


def _escalate_handler(state: AgentState) -> dict:
    """
    Handle escalation when max retries are reached.

    Args:
        state: Current agent state

    Returns:
        Updated state with failure status
    """
    current_file = state.get("current_file_path")
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 3)

    logger.warning(
        "escalate_handler",
        file=current_file,
        iterations=iteration_count,
        max=max_iterations,
    )

    return {
        "error_state": f"Max iterations ({max_iterations}) reached without passing validation",
        "approval_status": "FAILED",
    }


def create_simple_graph() -> StateGraph:
    """
    Create a simplified graph for testing (no checkpointer).

    Returns:
        Compiled LangGraph application
    """
    return create_graph(with_checkpointer=None)
