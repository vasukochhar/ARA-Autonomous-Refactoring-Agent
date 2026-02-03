"""
Docker Sandbox - Containerized code execution for safety.

Provides a secure environment for running generated code
without affecting the host system.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import subprocess
import tempfile
import os
import shutil
import time

import structlog

logger = structlog.get_logger()


@dataclass
class DockerConfig:
    """Configuration for Docker sandbox."""
    image: str = "python:3.11-slim"
    timeout: int = 30  # seconds
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    network_disabled: bool = True
    read_only: bool = False  # Some tests need to write


@dataclass
class ExecutionResult:
    """Result of code execution in sandbox."""
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
    timed_out: bool = False
    error: Optional[str] = None


class DockerSandbox:
    """
    Docker-based sandbox for safe code execution.
    
    Runs code in an isolated container with:
    - Limited CPU/memory
    - No network access
    - Timeout protection
    - Clean environment each run
    """
    
    def __init__(self, config: Optional[DockerConfig] = None):
        self.config = config or DockerConfig()
        self._container_id: Optional[str] = None
        self._temp_dir: Optional[str] = None
        self._docker_available = self._check_docker()
    
    def _check_docker(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("docker_not_available")
            return False
    
    def is_available(self) -> bool:
        """Check if Docker sandbox can be used."""
        return self._docker_available
    
    def execute_code(
        self,
        code: str,
        filename: str = "code.py",
        additional_files: Optional[Dict[str, str]] = None,
        pip_packages: Optional[List[str]] = None,
    ) -> ExecutionResult:
        """
        Execute Python code in a Docker container.
        
        Args:
            code: Python code to execute
            filename: Name for the code file
            additional_files: Extra files to include
            pip_packages: Packages to install before running
        
        Returns:
            ExecutionResult with stdout, stderr, exit code
        """
        if not self._docker_available:
            return self._execute_local_fallback(code, filename)
        
        start_time = time.time()
        
        try:
            # Create temp directory for code
            self._temp_dir = tempfile.mkdtemp(prefix="ara_sandbox_")
            
            # Write the code file
            code_path = os.path.join(self._temp_dir, filename)
            with open(code_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            # Write additional files
            if additional_files:
                for fname, content in additional_files.items():
                    fpath = os.path.join(self._temp_dir, fname)
                    os.makedirs(os.path.dirname(fpath), exist_ok=True)
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(content)
            
            # Build Docker command
            docker_cmd = self._build_docker_command(filename, pip_packages)
            
            # Run container
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                timeout=self.config.timeout,
                cwd=self._temp_dir,
            )
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return ExecutionResult(
                stdout=result.stdout.decode("utf-8", errors="replace"),
                stderr=result.stderr.decode("utf-8", errors="replace"),
                exit_code=result.returncode,
                execution_time_ms=execution_time,
            )
            
        except subprocess.TimeoutExpired:
            execution_time = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                stdout="",
                stderr="Execution timed out",
                exit_code=-1,
                execution_time_ms=execution_time,
                timed_out=True,
            )
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error("sandbox_execution_error", error=str(e))
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time_ms=execution_time,
                error=str(e),
            )
            
        finally:
            # Cleanup
            if self._temp_dir and os.path.exists(self._temp_dir):
                shutil.rmtree(self._temp_dir, ignore_errors=True)
    
    def _build_docker_command(
        self,
        filename: str,
        pip_packages: Optional[List[str]] = None,
    ) -> List[str]:
        """Build the Docker run command."""
        cmd = [
            "docker", "run",
            "--rm",  # Remove container after run
            f"--memory={self.config.memory_limit}",
            f"--cpus={self.config.cpu_limit}",
            "-v", f"{self._temp_dir}:/app",  # Mount code directory
            "-w", "/app",  # Working directory
        ]
        
        if self.config.network_disabled:
            cmd.append("--network=none")
        
        if self.config.read_only:
            cmd.append("--read-only")
        
        # Image and command
        cmd.append(self.config.image)
        
        # Build the execution command
        if pip_packages:
            pip_install = f"pip install -q {' '.join(pip_packages)} && "
        else:
            pip_install = ""
        
        cmd.extend(["bash", "-c", f"{pip_install}python {filename}"])
        
        return cmd
    
    def _execute_local_fallback(
        self,
        code: str,
        filename: str,
    ) -> ExecutionResult:
        """
        Fallback to local execution when Docker is not available.
        
        WARNING: This is less secure but allows functionality without Docker.
        """
        logger.warning("using_local_fallback_sandbox")
        
        start_time = time.time()
        temp_dir = None
        
        try:
            temp_dir = tempfile.mkdtemp(prefix="ara_local_sandbox_")
            code_path = os.path.join(temp_dir, filename)
            
            with open(code_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            result = subprocess.run(
                ["python", code_path],
                capture_output=True,
                timeout=self.config.timeout,
                cwd=temp_dir,
            )
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return ExecutionResult(
                stdout=result.stdout.decode("utf-8", errors="replace"),
                stderr=result.stderr.decode("utf-8", errors="replace"),
                exit_code=result.returncode,
                execution_time_ms=execution_time,
            )
            
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                stdout="",
                stderr="Execution timed out",
                exit_code=-1,
                execution_time_ms=self.config.timeout * 1000,
                timed_out=True,
            )
        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time_ms=0,
                error=str(e),
            )
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    def run_tests(
        self,
        code: str,
        test_code: str,
    ) -> ExecutionResult:
        """
        Run tests against generated code.
        
        Args:
            code: The generated code
            test_code: The test code to run
        
        Returns:
            ExecutionResult from running tests
        """
        return self.execute_code(
            code=test_code,
            filename="test_code.py",
            additional_files={"code.py": code},
            pip_packages=["pytest"],
        )
    
    def validate_syntax(self, code: str) -> ExecutionResult:
        """
        Validate Python syntax without executing.
        
        Args:
            code: Python code to validate
        
        Returns:
            ExecutionResult (exit_code 0 if valid)
        """
        validation_code = f'''
import ast
import sys

code = """
{code.replace('"""', "'''")}
"""

try:
    ast.parse(code)
    print("Syntax OK")
    sys.exit(0)
except SyntaxError as e:
    print(f"Syntax Error: {{e}}")
    sys.exit(1)
'''
        return self.execute_code(validation_code, filename="validate.py")


def get_sandbox() -> DockerSandbox:
    """Get a configured sandbox instance."""
    return DockerSandbox()


def execute_safely(code: str) -> ExecutionResult:
    """Execute code safely in a sandbox."""
    sandbox = get_sandbox()
    return sandbox.execute_code(code)
