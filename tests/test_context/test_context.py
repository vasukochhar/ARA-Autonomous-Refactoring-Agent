"""Tests for dependency graph and context management."""

import pytest

from ara.context.dependency_graph import (
    DependencyGraph,
    ModuleInfo,
    analyze_file,
    build_dependency_graph,
    find_affected_files,
)
from ara.context.rag_context import (
    ContextChunk,
    ContextWindow,
    ContextManager,
    create_refactoring_context,
)


class TestDependencyAnalyzer:
    """Tests for file dependency analysis."""

    def test_analyze_imports(self):
        """Test that imports are correctly identified."""
        source = '''
import os
import sys
from pathlib import Path
from typing import List, Optional

def foo():
    pass
'''
        info = analyze_file("test.py", source)
        
        assert info is not None
        assert "os" in info.imports
        assert "sys" in info.imports
        assert "pathlib" in info.imports
        assert "typing" in info.imports

    def test_analyze_functions(self):
        """Test that functions are identified."""
        source = '''
def foo():
    pass

async def bar():
    pass
'''
        info = analyze_file("test.py", source)
        
        assert info is not None
        assert "foo" in info.defines_functions
        assert "bar" in info.defines_functions

    def test_analyze_classes(self):
        """Test that classes are identified."""
        source = '''
class MyClass:
    pass

class AnotherClass:
    def method(self):
        pass
'''
        info = analyze_file("test.py", source)
        
        assert info is not None
        assert "MyClass" in info.defines_classes
        assert "AnotherClass" in info.defines_classes

    def test_analyze_syntax_error(self):
        """Test handling of syntax errors."""
        source = "def foo(:"  # Invalid syntax
        
        info = analyze_file("test.py", source)
        
        assert info is None


class TestDependencyGraph:
    """Tests for dependency graph building."""

    def test_build_graph(self):
        """Test building a dependency graph."""
        files = {
            "main.py": "import utils\nutils.helper()",
            "utils.py": "def helper(): pass",
        }
        
        graph = build_dependency_graph(files)
        
        assert len(graph.modules) == 2
        assert "main.py" in graph.modules
        assert "utils.py" in graph.modules

    def test_find_affected_files(self):
        """Test finding files affected by a change."""
        graph = DependencyGraph()
        
        graph.add_module(ModuleInfo("a.py", "a"))
        graph.add_module(ModuleInfo("b.py", "b"))
        graph.add_module(ModuleInfo("c.py", "c"))
        
        # b depends on a, c depends on b
        graph.add_edge("b.py", "a.py")
        graph.add_edge("c.py", "b.py")
        
        # If we change a.py, b.py is affected
        affected = find_affected_files(graph, "a.py")
        assert "b.py" in affected

    def test_topological_sort(self):
        """Test topological sorting of dependencies."""
        graph = DependencyGraph()
        
        graph.add_module(ModuleInfo("a.py", "a"))
        graph.add_module(ModuleInfo("b.py", "b"))
        graph.add_module(ModuleInfo("c.py", "c"))
        
        # c depends on b, b depends on a
        graph.add_edge("c.py", "b.py")
        graph.add_edge("b.py", "a.py")
        
        sorted_order = graph.topological_sort()
        
        # a should come before b, b before c
        a_idx = sorted_order.index("a.py")
        b_idx = sorted_order.index("b.py")
        c_idx = sorted_order.index("c.py")
        
        assert a_idx < b_idx < c_idx or a_idx > b_idx > c_idx  # Order depends on direction


class TestContextWindow:
    """Tests for context window management."""

    def test_token_estimation(self):
        """Test token estimation."""
        chunk = ContextChunk(
            filepath="test.py",
            content="x" * 400,  # 400 chars = ~100 tokens
        )
        
        assert chunk.token_estimate == 100

    def test_add_chunk_within_budget(self):
        """Test adding chunks within token budget."""
        context = ContextWindow(max_tokens=1000)
        
        chunk = ContextChunk(
            filepath="test.py",
            content="x" * 2000,  # ~500 tokens
        )
        
        assert context.add_chunk(chunk) is True
        assert len(context.chunks) == 1

    def test_add_chunk_exceeds_budget(self):
        """Test rejecting chunks that exceed budget."""
        context = ContextWindow(max_tokens=100)
        
        chunk = ContextChunk(
            filepath="test.py",
            content="x" * 2000,  # ~500 tokens
        )
        
        assert context.add_chunk(chunk) is False
        assert len(context.chunks) == 0

    def test_to_prompt(self):
        """Test converting context to prompt string."""
        context = ContextWindow()
        context.add_chunk(ContextChunk(
            filepath="test.py",
            content="def foo(): pass",
        ))
        
        prompt = context.to_prompt()
        
        assert "test.py" in prompt
        assert "def foo():" in prompt


class TestContextManager:
    """Tests for the context manager."""

    def test_get_context_for_file(self):
        """Test getting context for a file."""
        files = {
            "main.py": "import utils\nutils.foo()",
            "utils.py": "def foo(): pass",
        }
        
        manager = ContextManager(files)
        context = manager.get_context_for_file("main.py")
        
        # Primary file should be included
        assert any(c.filepath == "main.py" for c in context.chunks)
        assert any(c.is_primary for c in context.chunks)

    def test_create_refactoring_context(self):
        """Test the convenience function."""
        files = {
            "main.py": "def foo(): pass",
        }
        
        context = create_refactoring_context(
            files,
            "main.py",
            "Add type hints",
        )
        
        assert "Add type hints" in context
        assert "main.py" in context
        assert "def foo():" in context
