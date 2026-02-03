"""Tests for ARA state models."""

import pytest
from datetime import datetime

from ara.state.models import (
    FileContext,
    FileStatus,
    ValidationResult,
    RefactoringTarget,
    ReflectionNote,
    ApprovalStatus,
)


class TestFileContext:
    """Tests for FileContext model."""

    def test_create_minimal(self):
        """Test creating FileContext with minimal required fields."""
        ctx = FileContext(
            filepath="/path/to/file.py",
            original_content="print('hello')",
        )
        assert ctx.filepath == "/path/to/file.py"
        assert ctx.original_content == "print('hello')"
        assert ctx.modified_content is None
        assert ctx.diff is None
        assert ctx.status == FileStatus.PENDING.value
        assert ctx.error_message is None

    def test_create_full(self):
        """Test creating FileContext with all fields."""
        ctx = FileContext(
            filepath="/path/to/file.py",
            original_content="print('hello')",
            modified_content="print('world')",
            diff="@@ -1 +1 @@\n-print('hello')\n+print('world')",
            status=FileStatus.COMPLETED,
            error_message=None,
        )
        assert ctx.status == FileStatus.COMPLETED.value
        assert ctx.modified_content == "print('world')"

    def test_status_enum_values(self):
        """Test all FileStatus enum values."""
        assert FileStatus.PENDING.value == "PENDING"
        assert FileStatus.IN_PROGRESS.value == "IN_PROGRESS"
        assert FileStatus.COMPLETED.value == "COMPLETED"
        assert FileStatus.FAILED.value == "FAILED"
        assert FileStatus.SKIPPED.value == "SKIPPED"


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_create_passed(self):
        """Test creating a passing validation result."""
        result = ValidationResult(
            tool_name="pytest",
            passed=True,
            exit_code=0,
        )
        assert result.tool_name == "pytest"
        assert result.passed is True
        assert result.error_message is None
        assert result.failed_tests == []

    def test_create_failed(self):
        """Test creating a failing validation result."""
        result = ValidationResult(
            tool_name="pyright",
            passed=False,
            error_message="Type error: expected str, got int",
            exit_code=1,
        )
        assert result.passed is False
        assert "Type error" in result.error_message

    def test_failed_tests_list(self):
        """Test validation result with failed tests."""
        result = ValidationResult(
            tool_name="pytest",
            passed=False,
            failed_tests=["test_foo", "test_bar"],
        )
        assert len(result.failed_tests) == 2
        assert "test_foo" in result.failed_tests


class TestRefactoringTarget:
    """Tests for RefactoringTarget model."""

    def test_create_function_target(self):
        """Test creating a function refactoring target."""
        target = RefactoringTarget(
            filepath="/path/to/module.py",
            node_type="function",
            node_name="calculate_total",
            start_line=10,
            end_line=25,
            description="Add type hints to function",
        )
        assert target.node_type == "function"
        assert target.node_name == "calculate_total"
        assert target.start_line == 10
        assert target.end_line == 25


class TestReflectionNote:
    """Tests for ReflectionNote model."""

    def test_create_reflection(self):
        """Test creating a reflection note."""
        note = ReflectionNote(
            iteration=1,
            error_summary="Type mismatch in function call",
            suggested_fix="Cast integer to string using str()",
            relevant_error_lines=["line 15: expected str, got int"],
        )
        assert note.iteration == 1
        assert "Type mismatch" in note.error_summary
        assert len(note.relevant_error_lines) == 1


class TestApprovalStatus:
    """Tests for ApprovalStatus enum."""

    def test_status_values(self):
        """Test all ApprovalStatus enum values."""
        assert ApprovalStatus.PENDING.value == "PENDING"
        assert ApprovalStatus.APPROVED.value == "APPROVED"
        assert ApprovalStatus.REJECTED.value == "REJECTED"
