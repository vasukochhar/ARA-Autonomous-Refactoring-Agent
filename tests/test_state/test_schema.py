"""Tests for ARA agent state schema."""

import pytest

from ara.state.schema import AgentState, create_initial_state
from ara.state.models import ApprovalStatus


class TestAgentState:
    """Tests for AgentState TypedDict."""

    def test_create_initial_state(self):
        """Test creating initial state with factory function."""
        state = create_initial_state(
            refactoring_goal="Add type hints to all functions",
            max_iterations=5,
        )
        
        assert state["refactoring_goal"] == "Add type hints to all functions"
        assert state["max_iterations"] == 5
        assert state["iteration_count"] == 0
        assert state["files"] == {}
        assert state["dependency_graph"] == {}
        assert state["validation_history"] == []
        assert state["reflection_history"] == []
        assert state["approval_status"] == ApprovalStatus.PENDING.value
        assert state["workflow_id"] is not None

    def test_create_initial_state_with_workflow_id(self):
        """Test creating initial state with custom workflow ID."""
        state = create_initial_state(
            refactoring_goal="Migrate to Python 3",
            workflow_id="custom-workflow-123",
        )
        
        assert state["workflow_id"] == "custom-workflow-123"

    def test_state_fields_modifiable(self):
        """Test that state fields can be modified."""
        state = create_initial_state(refactoring_goal="Test")
        
        # Modify fields
        state["iteration_count"] = 2
        state["current_file_path"] = "/path/to/file.py"
        state["human_feedback"] = "Looks good!"
        
        assert state["iteration_count"] == 2
        assert state["current_file_path"] == "/path/to/file.py"
        assert state["human_feedback"] == "Looks good!"

    def test_validation_history_append(self):
        """Test that validation history can be appended."""
        from ara.state.models import ValidationResult
        
        state = create_initial_state(refactoring_goal="Test")
        
        result1 = ValidationResult(tool_name="ruff", passed=True)
        result2 = ValidationResult(tool_name="pytest", passed=False, error_message="Test failed")
        
        # Simulate reducer behavior (append)
        state["validation_history"] = state["validation_history"] + [result1]
        state["validation_history"] = state["validation_history"] + [result2]
        
        assert len(state["validation_history"]) == 2
        assert state["validation_history"][0].tool_name == "ruff"
        assert state["validation_history"][1].passed is False
