"""
Subprocess execution for ARA.

Provides safe subprocess execution with timeout, output capture,
and sandboxing support for running validation tools and scripts.
"""

import subprocess
import time
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field
import structlog

from ara.config import get_settings

logger = structlog.get_logger()


class CommandResult(BaseModel):
    """Result of a command execution."""

    command: str = Field(..., description="The command that was executed")
    exit_code: int = Field(..., description="Process exit code")
    stdout: str = Field(default="", description="Standard output")
    stderr: str = Field(default="", description="Standard error")
    execution_time_ms: int = Field(..., description="Execution time in milliseconds")
    timed_out: bool = Field(default=False, description="Whether the command timed out")
    success: bool = Field(..., description="Whether the command succeeded (exit code 0)")


def run_command(
    cmd: List[str],
    cwd: Optional[str] = None,
    timeout: Optional[int] = None,
    env: Optional[dict] = None,
    capture_output: bool = True,
) -> CommandResult:
    """
    Execute a command in a subprocess.

    This function provides a safe way to run external commands with
    proper timeout handling, output capture, and error handling.

    Args:
        cmd: Command and arguments as a list (e.g., ["python", "-m", "pytest"])
        cwd: Working directory for the command
        timeout: Timeout in seconds (default from settings)
        env: Additional environment variables
        capture_output: If True, capture stdout and stderr

    Returns:
        CommandResult with exit code, output, and timing information

    Example:
        >>> result = run_command(["ruff", "check", "src/"])
        >>> if result.success:
        ...     print("Linting passed!")
        ... else:
        ...     print(f"Errors: {result.stderr}")
    """
    settings = get_settings()
    timeout = timeout or settings.default_timeout

    # Validate working directory
    if cwd:
        cwd_path = Path(cwd)
        if not cwd_path.exists():
            raise FileNotFoundError(f"Working directory not found: {cwd}")
        if not cwd_path.is_dir():
            raise ValueError(f"Path is not a directory: {cwd}")

    # Build command string for logging
    command_str = " ".join(cmd)
    logger.info("command_start", command=command_str, cwd=cwd)

    start_time = time.perf_counter()
    timed_out = False

    try:
        process = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=timeout,
            capture_output=capture_output,
            text=True,
            env={**dict(subprocess.os.environ), **(env or {})},
        )

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        result = CommandResult(
            command=command_str,
            exit_code=process.returncode,
            stdout=process.stdout or "",
            stderr=process.stderr or "",
            execution_time_ms=execution_time_ms,
            timed_out=False,
            success=process.returncode == 0,
        )

        logger.info(
            "command_complete",
            command=command_str,
            exit_code=process.returncode,
            duration_ms=execution_time_ms,
        )

        return result

    except subprocess.TimeoutExpired as e:
        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        logger.warning(
            "command_timeout",
            command=command_str,
            timeout=timeout,
        )

        return CommandResult(
            command=command_str,
            exit_code=-1,
            stdout=e.stdout or "" if hasattr(e, "stdout") else "",
            stderr=e.stderr or "" if hasattr(e, "stderr") else "",
            execution_time_ms=execution_time_ms,
            timed_out=True,
            success=False,
        )

    except FileNotFoundError:
        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        logger.error("command_not_found", command=cmd[0])

        return CommandResult(
            command=command_str,
            exit_code=-1,
            stdout="",
            stderr=f"Command not found: {cmd[0]}",
            execution_time_ms=execution_time_ms,
            timed_out=False,
            success=False,
        )

    except Exception as e:
        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        logger.error("command_error", command=command_str, error=str(e))

        return CommandResult(
            command=command_str,
            exit_code=-1,
            stdout="",
            stderr=str(e),
            execution_time_ms=execution_time_ms,
            timed_out=False,
            success=False,
        )


def run_python_module(
    module: str,
    args: Optional[List[str]] = None,
    cwd: Optional[str] = None,
    timeout: Optional[int] = None,
) -> CommandResult:
    """
    Run a Python module as a subprocess.

    This is a convenience wrapper for running Python modules like
    pytest, ruff, pyright, etc.

    Args:
        module: Module name (e.g., "pytest", "ruff")
        args: Additional arguments to pass to the module
        cwd: Working directory
        timeout: Timeout in seconds

    Returns:
        CommandResult with execution details
    """
    import sys

    cmd = [sys.executable, "-m", module] + (args or [])
    return run_command(cmd, cwd=cwd, timeout=timeout)


def run_ruff_check(path: str, fix: bool = False) -> CommandResult:
    """
    Run ruff linter on a path.

    Args:
        path: File or directory to check
        fix: If True, apply automatic fixes

    Returns:
        CommandResult with linting results
    """
    args = ["check", path, "--output-format=json"]
    if fix:
        args.append("--fix")

    return run_python_module("ruff", args)


def run_pyright(path: str) -> CommandResult:
    """
    Run pyright type checker on a path.

    Args:
        path: File or directory to check

    Returns:
        CommandResult with type checking results
    """
    return run_python_module("pyright", [path, "--outputjson"])


def run_pytest(path: str, verbose: bool = True) -> CommandResult:
    """
    Run pytest on a path.

    Args:
        path: Test file or directory
        verbose: If True, run with verbose output

    Returns:
        CommandResult with test results
    """
    args = [path]
    if verbose:
        args.append("-v")
    args.append("--tb=short")

    return run_python_module("pytest", args, timeout=120)
