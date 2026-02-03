"""
Pydantic models for ARA state management.

These models provide type-safe, validated data structures for tracking
file contexts and validation results throughout the refactoring process.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FileStatus(str, Enum):
    """Status of a file in the refactoring pipeline."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ApprovalStatus(str, Enum):
    """Status of human approval."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FileContext(BaseModel):
    """
    Represents the state of a single file being refactored.

    This model tracks the original and modified content, diff output,
    and current processing status for each file in the refactoring task.
    """

    filepath: str = Field(..., description="Absolute path to the file")
    original_content: str = Field(..., description="Original file content before refactoring")
    modified_content: Optional[str] = Field(
        default=None, description="Modified file content after refactoring"
    )
    diff: Optional[str] = Field(
        default=None, description="Unified diff between original and modified content"
    )
    status: FileStatus = Field(
        default=FileStatus.PENDING, description="Current processing status"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if status is FAILED"
    )
    last_updated: datetime = Field(
        default_factory=datetime.now, description="Timestamp of last update"
    )

    model_config = ConfigDict(use_enum_values=True)


class ValidationResult(BaseModel):
    """
    Captures the output of validation tools.

    This model stores the results from static analysis, type checking,
    and unit tests run against the modified code.
    """

    tool_name: str = Field(..., description="Name of the validation tool (e.g., 'pyright', 'pytest')")
    passed: bool = Field(..., description="Whether validation passed")
    error_message: Optional[str] = Field(
        default=None, description="Error output if validation failed"
    )
    failed_tests: List[str] = Field(
        default_factory=list, description="List of failed test names"
    )
    execution_time_ms: Optional[int] = Field(
        default=None, description="Execution time in milliseconds"
    )
    exit_code: Optional[int] = Field(default=None, description="Process exit code")
    stdout: Optional[str] = Field(default=None, description="Standard output")
    stderr: Optional[str] = Field(default=None, description="Standard error output")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Timestamp of validation run"
    )


class RefactoringTarget(BaseModel):
    """
    Represents a specific refactoring target identified by the Analyzer.

    This could be a function, class, import statement, or any code pattern
    that needs to be transformed.
    """

    filepath: str = Field(..., description="File containing the target")
    node_type: str = Field(..., description="Type of AST node (e.g., 'function', 'class')")
    node_name: str = Field(..., description="Name of the target (e.g., function name)")
    start_line: int = Field(..., description="Starting line number")
    end_line: int = Field(..., description="Ending line number")
    description: Optional[str] = Field(
        default=None, description="Description of what needs to be changed"
    )


class ReflectionNote(BaseModel):
    """
    Captures the reflection/critique from the Reflector node.

    This provides structured feedback for the Generator to improve
    its next attempt.
    """

    iteration: int = Field(..., description="Iteration number when reflection was generated")
    error_summary: str = Field(..., description="Summary of what went wrong")
    suggested_fix: str = Field(..., description="Suggested approach to fix the issue")
    relevant_error_lines: List[str] = Field(
        default_factory=list, description="Relevant error messages from validation"
    )
    timestamp: datetime = Field(default_factory=datetime.now)
