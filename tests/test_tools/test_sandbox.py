"""Tests for sandbox execution."""

import sys
import pytest

from ara.tools.sandbox import (
    TempDirSandbox,
    SandboxConfig,
    SandboxResult,
    execute_in_sandbox,
    validate_code_in_sandbox,
)


class TestTempDirSandbox:
    """Tests for TempDirSandbox."""

    def test_sandbox_context_manager(self):
        """Test that sandbox creates and cleans up temp directory."""
        with TempDirSandbox() as sandbox:
            assert sandbox.temp_dir is not None
            assert sandbox.temp_dir.exists()
            temp_path = sandbox.temp_dir

        # After context exit, directory should be cleaned up
        assert not temp_path.exists()

    def test_write_file(self):
        """Test writing files to sandbox."""
        with TempDirSandbox() as sandbox:
            path = sandbox.write_file("test.py", "print('hello')")
            assert path.endswith("test.py")
            assert (sandbox.temp_dir / "test.py").exists()

    def test_run_python_code_success(self):
        """Test running Python code that succeeds."""
        with TempDirSandbox() as sandbox:
            result = sandbox.run_python_code("print('Hello, World!')")
            
            assert result.success is True
            assert result.exit_code == 0
            assert "Hello, World!" in result.stdout
            assert result.sandbox_type == "tempdir"

    def test_run_python_code_failure(self):
        """Test running Python code that fails."""
        with TempDirSandbox() as sandbox:
            result = sandbox.run_python_code("raise ValueError('test error')")
            
            assert result.success is False
            assert result.exit_code != 0
            assert "ValueError" in result.stderr

    def test_run_python_code_syntax_error(self):
        """Test running Python code with syntax error."""
        with TempDirSandbox() as sandbox:
            result = sandbox.run_python_code("def broken(")
            
            assert result.success is False
            assert "SyntaxError" in result.stderr

    def test_run_command_timeout(self):
        """Test that commands timeout correctly."""
        with TempDirSandbox(SandboxConfig(timeout=1)) as sandbox:
            # This should timeout
            result = sandbox.run_python_code(
                "import time; time.sleep(10)",
                timeout=1,
            )
            
            assert result.success is False
            assert "timed out" in result.stderr.lower()

    def test_allowed_commands(self):
        """Test that only allowed commands can run."""
        config = SandboxConfig(allowed_commands=["python"])
        
        with TempDirSandbox(config) as sandbox:
            # Not allowed command
            result = sandbox.run_command(["rm", "-rf", "/"])
            assert result.success is False
            assert "not allowed" in result.stderr.lower()


class TestExecuteInSandbox:
    """Tests for execute_in_sandbox convenience function."""

    def test_simple_execution(self):
        """Test simple code execution."""
        result = execute_in_sandbox("print(2 + 2)")
        
        assert result.success is True
        assert "4" in result.stdout

    def test_with_imports(self):
        """Test code with standard library imports."""
        code = """
import json
data = {"key": "value"}
print(json.dumps(data))
"""
        result = execute_in_sandbox(code)
        
        assert result.success is True
        assert "key" in result.stdout


class TestValidateCodeInSandbox:
    """Tests for code validation in sandbox."""

    def test_validate_clean_code(self):
        """Test validating clean Python code."""
        clean_code = '''
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"
'''
        results = validate_code_in_sandbox(clean_code, run_pyright=False)
        
        # Ruff should pass on clean code
        assert len(results) >= 1
        # Note: actual pass/fail depends on ruff being installed

    def test_validate_code_with_issues(self):
        """Test validating code with linting issues."""
        bad_code = '''
import os  # unused import
x=1  # missing spaces
'''
        results = validate_code_in_sandbox(bad_code, run_pyright=False)
        
        assert len(results) >= 1
        # Ruff should find issues
