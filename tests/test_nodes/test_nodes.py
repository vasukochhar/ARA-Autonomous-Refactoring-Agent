"""Tests for LangGraph nodes."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from ara.state.schema import create_initial_state, AgentState
from ara.state.models import FileContext, FileStatus, ValidationResult


class TestAnalyzerNode:
    """Tests for the Analyzer node."""

    def test_analyzer_no_files(self):
        """Test analyzer with no files returns error."""
        from ara.nodes.analyzer import analyzer_node
        
        state = create_initial_state("Add type hints")
        result = analyzer_node(state)
        
        assert "error_state" in result
        assert "No files" in result["error_state"]

    @patch("ara.nodes.analyzer.get_llm")
    def test_analyzer_with_files(self, mock_get_llm):
        """Test analyzer with files calls LLM."""
        from ara.nodes.analyzer import analyzer_node
        
        # Mock LLM response
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Analysis: found 2 targets")
        mock_get_llm.return_value = mock_llm
        
        state = create_initial_state("Add type hints")
        state["files"] = {
            "test.py": FileContext(
                filepath="test.py",
                original_content="def foo(): pass",
            )
        }
        
        result = analyzer_node(state)
        
        assert result.get("current_file_path") == "test.py"
        mock_llm.invoke.assert_called_once()


class TestGeneratorNode:
    """Tests for the Generator node."""

    def test_generator_no_file(self):
        """Test generator with no current file returns error."""
        from ara.nodes.generator import generator_node
        
        state = create_initial_state("Add type hints")
        result = generator_node(state)
        
        assert "error_state" in result

    @patch("ara.nodes.generator.get_llm")
    def test_generator_with_file(self, mock_get_llm):
        """Test generator generates code."""
        from ara.nodes.generator import generator_node
        
        # Mock LLM response
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="def foo() -> None:\n    pass")
        mock_get_llm.return_value = mock_llm
        
        state = create_initial_state("Add type hints")
        state["files"] = {
            "test.py": FileContext(
                filepath="test.py",
                original_content="def foo(): pass",
            )
        }
        state["current_file_path"] = "test.py"
        
        result = generator_node(state)
        
        assert "generated_code_snippet" in result
        assert "files" in result
        mock_llm.invoke.assert_called_once()

    def test_clean_code_response(self):
        """Test code response cleaning."""
        from ara.nodes.generator import _clean_code_response
        
        # With markdown fences
        code = "```python\ndef foo(): pass\n```"
        assert _clean_code_response(code) == "def foo(): pass"
        
        # Without fences
        code2 = "def bar(): return 1"
        assert _clean_code_response(code2) == "def bar(): return 1"


class TestValidatorNode:
    """Tests for the Validator node."""

    def test_validator_no_code(self):
        """Test validator with no code returns failure."""
        from ara.nodes.validator import validator_node
        
        state = create_initial_state("Add type hints")
        result = validator_node(state)
        
        assert "validation_history" in result
        assert len(result["validation_history"]) > 0
        assert result["validation_history"][0].passed is False

    def test_validator_syntax_check(self):
        """Test validator checks syntax."""
        from ara.nodes.validator import _check_syntax
        
        # Valid code
        result = _check_syntax("def foo(): pass")
        assert result.passed is True
        assert result.tool_name == "syntax_check"
        
        # Invalid code
        result = _check_syntax("def foo(")
        assert result.passed is False
        assert "SyntaxError" in result.error_message

    def test_validator_with_valid_code(self):
        """Test validator with valid code."""
        from ara.nodes.validator import validator_node
        
        state = create_initial_state("Add type hints")
        state["generated_code_snippet"] = "def foo() -> None:\n    pass\n"
        
        result = validator_node(state)
        
        assert "validation_history" in result
        # Syntax check should pass
        syntax_result = result["validation_history"][0]
        assert syntax_result.passed is True


class TestReflectorNode:
    """Tests for the Reflector node."""

    def test_reflector_no_history(self):
        """Test reflector with no validation history."""
        from ara.nodes.reflector import reflector_node
        
        state = create_initial_state("Add type hints")
        result = reflector_node(state)
        
        assert "iteration_count" in result
        assert result["iteration_count"] == 1

    @patch("ara.nodes.reflector.get_llm")
    def test_reflector_with_failures(self, mock_get_llm):
        """Test reflector analyzes failures."""
        from ara.nodes.reflector import reflector_node
        
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="Error Summary: Type mismatch\nSuggested Fix: Cast to string"
        )
        mock_get_llm.return_value = mock_llm
        
        state = create_initial_state("Add type hints")
        state["generated_code_snippet"] = "def foo(): pass"
        state["validation_history"] = [
            ValidationResult(
                tool_name="pyright",
                passed=False,
                error_message="Type error at line 5",
            )
        ]
        
        result = reflector_node(state)
        
        assert result["iteration_count"] == 1
        assert "reflection_history" in result
        mock_llm.invoke.assert_called_once()

    def test_build_error_context(self):
        """Test error context building."""
        from ara.nodes.reflector import _build_error_context
        
        failures = [
            ValidationResult(
                tool_name="ruff",
                passed=False,
                error_message="Unused import",
            )
        ]
        
        context = _build_error_context(failures)
        
        assert "ruff" in context
        assert "Unused import" in context


class TestRouter:
    """Tests for graph routing logic."""

    def test_route_success(self):
        """Test routing to success on passed validation."""
        from ara.graph.router import route_after_validation
        
        state = create_initial_state("Add type hints")
        state["validation_history"] = [
            ValidationResult(tool_name="ruff", passed=True),
            ValidationResult(tool_name="pyright", passed=True),
        ]
        
        result = route_after_validation(state)
        assert result == "success"

    def test_route_reflect(self):
        """Test routing to reflect on failed validation."""
        from ara.graph.router import route_after_validation
        
        state = create_initial_state("Add type hints")
        state["iteration_count"] = 0
        state["max_iterations"] = 3
        state["validation_history"] = [
            ValidationResult(tool_name="ruff", passed=False),
        ]
        
        result = route_after_validation(state)
        assert result == "reflect"

    def test_route_escalate(self):
        """Test routing to escalate on max retries."""
        from ara.graph.router import route_after_validation
        
        state = create_initial_state("Add type hints")
        state["iteration_count"] = 3
        state["max_iterations"] = 3
        state["validation_history"] = [
            ValidationResult(tool_name="ruff", passed=False),
        ]
        
        result = route_after_validation(state)
        assert result == "escalate"
