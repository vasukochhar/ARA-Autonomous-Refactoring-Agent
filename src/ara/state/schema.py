"""
AgentState schema for LangGraph state management.

This TypedDict defines the central state object passed between graph nodes,
serving as the "brain" of the agent with all context required for decision-making.
"""

import operator
from typing import Annotated, Dict, List, Optional, TypedDict

from ara.state.models import (
    ApprovalStatus,
    FileContext,
    ReflectionNote,
    RefactoringTarget,
    ValidationResult,
)


def _append_list(existing: List, new: List) -> List:
    """Reducer function that appends new items to existing list."""
    return existing + new


class AgentState(TypedDict, total=False):
    """
    The central state object passed between graph nodes.

    This state schema uses LangGraph's annotation system for reducers,
    allowing specific fields to function as append-only logs crucial
    for retaining the history of attempts for the reflection process.

    Attributes:
        files: Map of filepath to FileContext for all files being processed
        dependency_graph: Adjacency list mapping files to their dependents
        refactoring_targets: List of identified targets from the Analyzer
        refactoring_goal: Natural language description of the refactoring task
        current_file_path: Path to the file currently being processed
        generated_code_snippet: Latest generated code from the Generator
        validation_history: Append-only log of all validation results
        reflection_history: Append-only log of all reflection notes
        iteration_count: Current retry iteration (for self-correction loop)
        max_iterations: Maximum allowed iterations before escalation
        human_feedback: Feedback provided by human reviewer
        approval_status: Current approval status (PENDING/APPROVED/REJECTED)
        workflow_id: Unique identifier for this workflow instance
        error_state: Any unrecoverable error that occurred
    """

    # Repository Context
    files: Dict[str, FileContext]
    dependency_graph: Dict[str, List[str]]
    refactoring_targets: List[RefactoringTarget]

    # Task Definition
    refactoring_goal: str
    current_file_path: Optional[str]

    # Execution Artifacts
    generated_code_snippet: Optional[str]
    generated_codemod: Optional[str]  # LibCST transformer code
    refactoring_summary: Optional[str]  # Plain English explanation of changes

    # Validation History (append-only via reducer)
    validation_history: Annotated[List[ValidationResult], operator.add]

    # Reflection History (append-only via reducer)
    reflection_history: Annotated[List[ReflectionNote], operator.add]

    # Control Flow Metrics
    iteration_count: int
    max_iterations: int

    # Human Interaction
    human_feedback: Optional[str]
    approval_status: str  # Use string to allow serialization

    # Workflow Metadata
    workflow_id: Optional[str]
    error_state: Optional[str]

    # Multi-File Processing
    file_queue: List[str]  # Ordered list of files to process
    file_queue_index: int  # Current position in file queue

    # Cycle Detection (Phase 7)
    code_hashes: List[str]  # Hash of generated code to detect oscillation


def create_initial_state(
    refactoring_goal: str,
    max_iterations: int = 3,
    workflow_id: Optional[str] = None,
) -> AgentState:
    """
    Create an initial AgentState with default values.

    Args:
        refactoring_goal: Natural language description of the refactoring task
        max_iterations: Maximum retry iterations for self-correction
        workflow_id: Optional unique identifier for the workflow

    Returns:
        A new AgentState with initialized default values
    """
    import uuid

    return AgentState(
        files={},
        dependency_graph={},
        refactoring_targets=[],
        refactoring_goal=refactoring_goal,
        current_file_path=None,
        generated_code_snippet=None,
        generated_codemod=None,
        refactoring_summary=None,
        validation_history=[],
        reflection_history=[],
        iteration_count=0,
        max_iterations=max_iterations,
        human_feedback=None,
        approval_status=ApprovalStatus.PENDING.value,
        workflow_id=workflow_id or str(uuid.uuid4()),
        error_state=None,
        file_queue=[],
        file_queue_index=0,
        code_hashes=[],
    )
