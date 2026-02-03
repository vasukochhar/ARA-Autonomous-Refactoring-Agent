"""Context module - Dependency analysis and RAG context management."""

from ara.context.dependency_graph import (
    DependencyGraph,
    ModuleInfo,
    DependencyAnalyzer,
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

__all__ = [
    # Dependency Graph
    "DependencyGraph",
    "ModuleInfo",
    "DependencyAnalyzer",
    "analyze_file",
    "build_dependency_graph",
    "find_affected_files",
    # RAG Context
    "ContextChunk",
    "ContextWindow",
    "ContextManager",
    "create_refactoring_context",
]
