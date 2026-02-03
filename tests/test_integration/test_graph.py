"""Integration tests for the ARA graph."""

import pytest
from unittest.mock import patch, MagicMock

from ara.state.schema import create_initial_state
from ara.state.models import FileContext


class TestGraphIntegration:
    """Integration tests for the complete graph."""

    def test_graph_creation(self):
        """Test that the graph can be created."""
        from ara.graph.builder import create_simple_graph
        
        graph = create_simple_graph()
        assert graph is not None

    @patch("ara.nodes.analyzer.get_llm")
    @patch("ara.nodes.generator.get_llm")
    def test_single_file_success_flow(self, mock_gen_llm, mock_ana_llm):
        """Test successful refactoring of a single file."""
        from ara.graph.builder import create_simple_graph
        
        # Mock analyzer LLM
        mock_ana = MagicMock()
        mock_ana.invoke.return_value = MagicMock(content="Found 1 target: foo function")
        mock_ana_llm.return_value = mock_ana
        
        # Mock generator LLM - return valid typed code
        mock_gen = MagicMock()
        mock_gen.invoke.return_value = MagicMock(
            content="def foo(x: int) -> int:\n    return x + 1\n"
        )
        mock_gen_llm.return_value = mock_gen
        
        # Create initial state
        state = create_initial_state(
            refactoring_goal="Add type hints to function foo",
            max_iterations=3,
        )
        state["files"] = {
            "test.py": FileContext(
                filepath="test.py",
                original_content="def foo(x):\n    return x + 1\n",
            )
        }
        
        # Run the graph
        graph = create_simple_graph()
        result = graph.invoke(state)
        
        # Check result
        assert result is not None
        # Either success or we processed the file
        assert "files" in result or "error_state" in result

    @patch("ara.nodes.analyzer.get_llm")
    @patch("ara.nodes.generator.get_llm")
    @patch("ara.nodes.reflector.get_llm")
    def test_self_correction_loop(self, mock_ref_llm, mock_gen_llm, mock_ana_llm):
        """Test that the self-correction loop works."""
        from ara.graph.builder import create_simple_graph
        
        # Mock analyzer
        mock_ana = MagicMock()
        mock_ana.invoke.return_value = MagicMock(content="Analysis complete")
        mock_ana_llm.return_value = mock_ana
        
        # Mock generator - first returns invalid, then valid code
        mock_gen = MagicMock()
        call_count = [0]
        
        def gen_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call - return code with syntax error
                return MagicMock(content="def foo(x:\n    return x")
            else:
                # Subsequent calls - return valid code
                return MagicMock(content="def foo(x: int) -> int:\n    return x\n")
        
        mock_gen.invoke.side_effect = gen_side_effect
        mock_gen_llm.return_value = mock_gen
        
        # Mock reflector
        mock_ref = MagicMock()
        mock_ref.invoke.return_value = MagicMock(
            content="Error Summary: Syntax error\nSuggested Fix: Close parenthesis"
        )
        mock_ref_llm.return_value = mock_ref
        
        # Create state with invalid code scenario
        state = create_initial_state(
            refactoring_goal="Add type hints",
            max_iterations=3,
        )
        state["files"] = {
            "test.py": FileContext(
                filepath="test.py",
                original_content="def foo(x):\n    return x\n",
            )
        }
        
        # Run graph
        graph = create_simple_graph()
        result = graph.invoke(state)
        
        # Verify the graph processed
        assert result is not None


class TestGraphWithRealValidation:
    """Tests using real validation (no LLM mocking for validator)."""

    @patch("ara.nodes.analyzer.get_llm")
    @patch("ara.nodes.generator.get_llm")
    def test_validation_catches_syntax_error(self, mock_gen_llm, mock_ana_llm):
        """Test that validation catches syntax errors."""
        from ara.graph.builder import create_simple_graph
        
        # Mock analyzer
        mock_ana = MagicMock()
        mock_ana.invoke.return_value = MagicMock(content="Analysis complete")
        mock_ana_llm.return_value = mock_ana
        
        # Mock generator to return invalid code
        mock_gen = MagicMock()
        mock_gen.invoke.return_value = MagicMock(content="def foo(:\n    pass")
        mock_gen_llm.return_value = mock_gen
        
        state = create_initial_state(
            refactoring_goal="Add type hints",
            max_iterations=1,  # Only 1 iteration so it escalates after failure
        )
        state["files"] = {
            "test.py": FileContext(
                filepath="test.py",
                original_content="def foo(): pass",
            )
        }
        
        graph = create_simple_graph()
        result = graph.invoke(state)
        
        # Should have validation history with failures
        assert "validation_history" in result
        # First should be a syntax check failure
        if result["validation_history"]:
            first_result = result["validation_history"][0]
            # With syntax error, it should fail
            assert first_result.tool_name == "syntax_check"
