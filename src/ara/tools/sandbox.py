"""
Sandboxed code execution for ARA.

Provides safe execution environments for running generated code,
transformations, and validation tools without risking the host system.
"""

import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field

import structlog

from ara.config import get_settings
from ara.tools.subprocess_runner import CommandResult

logger = structlog.get_logger()


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""

    timeout: int = 30
    max_memory_mb: int = 512
    max_output_size: int = 1_000_000  # 1MB
    allowed_commands: List[str] = field(
        default_factory=lambda: ["python", "ruff", "pyright", "pytest"]
    )
    use_docker: bool = False
    docker_image: str = "python:3.11-slim"


@dataclass
class SandboxResult:
    """Result of sandboxed execution."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
    sandbox_type: str  # "local", "tempdir", "docker"
    working_dir: Optional[str] = None


class TempDirSandbox:
    """
    Sandbox that executes code in an isolated temporary directory.

    This provides basic isolation by:
    1. Creating a temporary working directory
    2. Copying only necessary files
    3. Running commands in the isolated directory
    4. Cleaning up after execution
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self.temp_dir: Optional[Path] = None

    def __enter__(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="ara_sandbox_"))
        logger.info("sandbox_created", path=str(self.temp_dir))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.info("sandbox_cleaned", path=str(self.temp_dir))

    def copy_file(self, source: str, dest_name: Optional[str] = None) -> str:
        """
        Copy a file into the sandbox.

        Args:
            source: Path to the source file
            dest_name: Optional name for the file in sandbox

        Returns:
            Path to the file in the sandbox
        """
        if not self.temp_dir:
            raise RuntimeError("Sandbox not initialized. Use context manager.")

        source_path = Path(source)
        dest_name = dest_name or source_path.name
        dest_path = self.temp_dir / dest_name

        shutil.copy2(source_path, dest_path)
        logger.debug("file_copied_to_sandbox", source=source, dest=str(dest_path))

        return str(dest_path)

    def write_file(self, filename: str, content: str) -> str:
        """
        Write content to a file in the sandbox.

        Args:
            filename: Name of the file to create
            content: Content to write

        Returns:
            Path to the created file
        """
        if not self.temp_dir:
            raise RuntimeError("Sandbox not initialized. Use context manager.")

        file_path = self.temp_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        logger.debug("file_written_to_sandbox", path=str(file_path))
        return str(file_path)

    def run_command(
        self,
        cmd: List[str],
        timeout: Optional[int] = None,
    ) -> SandboxResult:
        """
        Run a command in the sandbox environment.

        Args:
            cmd: Command and arguments to run
            timeout: Timeout in seconds

        Returns:
            SandboxResult with execution details
        """
        if not self.temp_dir:
            raise RuntimeError("Sandbox not initialized. Use context manager.")

        timeout = timeout or self.config.timeout

        # Validate command
        if cmd[0] not in self.config.allowed_commands:
            # Check if it's a python -m command
            if not (cmd[0] == sys.executable or 
                    (len(cmd) > 2 and cmd[1] == "-m" and cmd[2] in self.config.allowed_commands)):
                logger.warning("command_not_allowed", command=cmd[0])
                return SandboxResult(
                    success=False,
                    stdout="",
                    stderr=f"Command not allowed: {cmd[0]}",
                    exit_code=-1,
                    execution_time_ms=0,
                    sandbox_type="tempdir",
                )

        import time
        start_time = time.perf_counter()

        try:
            process = subprocess.run(
                cmd,
                cwd=self.temp_dir,
                timeout=timeout,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(self.temp_dir),
                },
            )

            execution_time_ms = int((time.perf_counter() - start_time) * 1000)

            # Truncate output if too large
            stdout = process.stdout[:self.config.max_output_size]
            stderr = process.stderr[:self.config.max_output_size]

            return SandboxResult(
                success=process.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=process.returncode,
                execution_time_ms=execution_time_ms,
                sandbox_type="tempdir",
                working_dir=str(self.temp_dir),
            )

        except subprocess.TimeoutExpired:
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                exit_code=-1,
                execution_time_ms=execution_time_ms,
                sandbox_type="tempdir",
                working_dir=str(self.temp_dir),
            )

        except Exception as e:
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("sandbox_execution_error", error=str(e))
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time_ms=execution_time_ms,
                sandbox_type="tempdir",
            )

    def run_python_code(
        self,
        code: str,
        filename: str = "script.py",
        timeout: Optional[int] = None,
    ) -> SandboxResult:
        """
        Run Python code in the sandbox.

        Args:
            code: Python code to execute
            filename: Name for the script file
            timeout: Timeout in seconds

        Returns:
            SandboxResult with execution details
        """
        script_path = self.write_file(filename, code)
        return self.run_command([sys.executable, script_path], timeout=timeout)

    def run_libcst_transform(
        self,
        source_code: str,
        transformer_code: str,
        timeout: Optional[int] = None,
    ) -> SandboxResult:
        """
        Run a LibCST transformation in the sandbox.

        Args:
            source_code: The source code to transform
            transformer_code: The LibCST transformer class code
            timeout: Timeout in seconds

        Returns:
            SandboxResult with transformed code in stdout
        """
        # Write source file
        self.write_file("source.py", source_code)

        # Create runner script
        runner_script = f'''
import libcst as cst

# Transformer definition
{transformer_code}

# Read source
with open("source.py", "r") as f:
    source = f.read()

# Parse and transform
tree = cst.parse_module(source)
transformer = globals()[next(
    name for name, obj in globals().items() 
    if isinstance(obj, type) and issubclass(obj, cst.CSTTransformer) and obj != cst.CSTTransformer
)]()
modified_tree = tree.visit(transformer)

# Output result
print(modified_tree.code)
'''
        return self.run_python_code(runner_script, "run_transform.py", timeout=timeout)


def execute_in_sandbox(
    code: str,
    config: Optional[SandboxConfig] = None,
) -> SandboxResult:
    """
    Convenience function to execute Python code in a sandbox.

    Args:
        code: Python code to execute
        config: Optional sandbox configuration

    Returns:
        SandboxResult with execution details
    """
    with TempDirSandbox(config) as sandbox:
        return sandbox.run_python_code(code)


def validate_code_in_sandbox(
    code: str,
    run_ruff: bool = True,
    run_pyright: bool = True,
    config: Optional[SandboxConfig] = None,
) -> List[SandboxResult]:
    """
    Validate Python code using linting and type checking in a sandbox.

    Args:
        code: Python code to validate
        run_ruff: Whether to run ruff linting
        run_pyright: Whether to run pyright type checking
        config: Optional sandbox configuration

    Returns:
        List of SandboxResult for each validation tool
    """
    results = []

    with TempDirSandbox(config) as sandbox:
        script_path = sandbox.write_file("code.py", code)

        if run_ruff:
            ruff_result = sandbox.run_command(
                [sys.executable, "-m", "ruff", "check", "code.py"]
            )
            results.append(ruff_result)

        if run_pyright:
            pyright_result = sandbox.run_command(
                [sys.executable, "-m", "pyright", "code.py"]
            )
            results.append(pyright_result)

    return results
