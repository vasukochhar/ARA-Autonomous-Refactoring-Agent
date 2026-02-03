"""
RAG Context Manager - Manage context for LLM prompts.

Provides utilities to extract relevant code context without exceeding
token limits, using dependency analysis and symbol resolution.
"""

from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

import structlog

from ara.context.dependency_graph import (
    build_dependency_graph,
    find_affected_files,
    DependencyGraph,
    ModuleInfo,
)

logger = structlog.get_logger()


# Approximate token counts (rough estimates)
CHARS_PER_TOKEN = 4  # Average characters per token
DEFAULT_MAX_TOKENS = 8000  # Max tokens for context


@dataclass
class ContextChunk:
    """A chunk of code context to include in the prompt."""
    
    filepath: str
    content: str
    relevance_score: float = 1.0
    is_primary: bool = False  # Is this the file being transformed?
    line_range: Optional[Tuple[int, int]] = None  # If partial file
    
    @property
    def token_estimate(self) -> int:
        """Estimate the number of tokens in this chunk."""
        return len(self.content) // CHARS_PER_TOKEN


@dataclass
class ContextWindow:
    """A curated context window for LLM prompts."""
    
    chunks: List[ContextChunk] = field(default_factory=list)
    max_tokens: int = DEFAULT_MAX_TOKENS
    
    @property
    def total_tokens(self) -> int:
        """Total estimated tokens in the context."""
        return sum(c.token_estimate for c in self.chunks)
    
    @property
    def remaining_tokens(self) -> int:
        """Remaining token budget."""
        return max(0, self.max_tokens - self.total_tokens)
    
    def add_chunk(self, chunk: ContextChunk) -> bool:
        """
        Add a chunk if there's room in the token budget.
        
        Args:
            chunk: Context chunk to add
        
        Returns:
            True if added, False if no room
        """
        if chunk.token_estimate <= self.remaining_tokens:
            self.chunks.append(chunk)
            return True
        return False
    
    def to_prompt(self) -> str:
        """Convert context to a formatted prompt string."""
        parts = []
        
        for chunk in self.chunks:
            header = f"=== {chunk.filepath}"
            if chunk.line_range:
                header += f" (lines {chunk.line_range[0]}-{chunk.line_range[1]})"
            header += " ==="
            
            parts.append(header)
            parts.append(chunk.content)
            parts.append("")
        
        return "\n".join(parts)


class ContextManager:
    """
    Manages context extraction for LLM prompts.
    
    Selects relevant code based on dependencies, symbol usage,
    and token budget constraints.
    """
    
    def __init__(
        self,
        files: Dict[str, str],
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        """
        Initialize the context manager.
        
        Args:
            files: Dict mapping filepath to source code
            max_tokens: Maximum tokens for context
        """
        self.files = files
        self.max_tokens = max_tokens
        self._graph: Optional[DependencyGraph] = None
    
    @property
    def dependency_graph(self) -> DependencyGraph:
        """Get or build the dependency graph."""
        if self._graph is None:
            self._graph = build_dependency_graph(self.files)
        return self._graph
    
    def get_context_for_file(
        self,
        target_file: str,
        include_dependencies: bool = True,
        include_dependents: bool = False,
    ) -> ContextWindow:
        """
        Get context for transforming a specific file.
        
        Args:
            target_file: The file being transformed
            include_dependencies: Include files this file depends on
            include_dependents: Include files that depend on this file
        
        Returns:
            ContextWindow with relevant code chunks
        """
        context = ContextWindow(max_tokens=self.max_tokens)
        
        # Always include the target file (primary)
        if target_file in self.files:
            primary_chunk = ContextChunk(
                filepath=target_file,
                content=self.files[target_file],
                relevance_score=1.0,
                is_primary=True,
            )
            context.add_chunk(primary_chunk)
        
        # Add dependencies
        if include_dependencies:
            dependencies = self.dependency_graph.get_dependencies(target_file)
            for dep in dependencies:
                if dep in self.files:
                    chunk = ContextChunk(
                        filepath=dep,
                        content=self.files[dep],
                        relevance_score=0.8,
                    )
                    context.add_chunk(chunk)
        
        # Add dependents
        if include_dependents:
            dependents = self.dependency_graph.get_dependents(target_file)
            for dep in dependents:
                if dep in self.files:
                    chunk = ContextChunk(
                        filepath=dep,
                        content=self.files[dep],
                        relevance_score=0.6,
                    )
                    context.add_chunk(chunk)
        
        return context
    
    def get_context_for_symbol(
        self,
        symbol_name: str,
        target_file: str,
    ) -> ContextWindow:
        """
        Get context relevant to a specific symbol.
        
        Args:
            symbol_name: Name of the function/class/variable
            target_file: The file containing the symbol
        
        Returns:
            ContextWindow with relevant code
        """
        context = ContextWindow(max_tokens=self.max_tokens)
        
        # Include the target file
        if target_file in self.files:
            primary_chunk = ContextChunk(
                filepath=target_file,
                content=self.files[target_file],
                relevance_score=1.0,
                is_primary=True,
            )
            context.add_chunk(primary_chunk)
        
        # Find files that use this symbol
        for filepath, content in self.files.items():
            if filepath == target_file:
                continue
            
            if symbol_name in content:
                # Extract relevant portion
                relevant = self._extract_symbol_usage(content, symbol_name)
                if relevant:
                    chunk = ContextChunk(
                        filepath=filepath,
                        content=relevant,
                        relevance_score=0.7,
                    )
                    context.add_chunk(chunk)
        
        return context
    
    def _extract_symbol_usage(
        self,
        content: str,
        symbol_name: str,
        context_lines: int = 5,
    ) -> Optional[str]:
        """
        Extract lines around usages of a symbol.
        
        Args:
            content: File content
            symbol_name: Symbol to find
            context_lines: Number of lines before/after to include
        
        Returns:
            Extracted content or None
        """
        lines = content.split("\n")
        relevant_lines: Set[int] = set()
        
        for i, line in enumerate(lines):
            if symbol_name in line:
                # Add context around the usage
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                relevant_lines.update(range(start, end))
        
        if not relevant_lines:
            return None
        
        # Build output with line ranges
        sorted_lines = sorted(relevant_lines)
        result_parts = []
        current_range = [sorted_lines[0], sorted_lines[0]]
        
        for line_num in sorted_lines[1:]:
            if line_num == current_range[1] + 1:
                current_range[1] = line_num
            else:
                # Output current range
                result_parts.append(
                    f"# Lines {current_range[0]+1}-{current_range[1]+1}:"
                )
                result_parts.extend(lines[current_range[0]:current_range[1]+1])
                result_parts.append("...")
                current_range = [line_num, line_num]
        
        # Output final range
        result_parts.append(f"# Lines {current_range[0]+1}-{current_range[1]+1}:")
        result_parts.extend(lines[current_range[0]:current_range[1]+1])
        
        return "\n".join(result_parts)


def create_refactoring_context(
    files: Dict[str, str],
    target_file: str,
    refactoring_goal: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """
    Create a context string for refactoring a file.
    
    Convenience function that builds context and formats it for prompts.
    
    Args:
        files: Dict mapping filepath to source code
        target_file: File to refactor
        refactoring_goal: The refactoring objective
        max_tokens: Max tokens for context
    
    Returns:
        Formatted context string
    """
    manager = ContextManager(files, max_tokens)
    context = manager.get_context_for_file(target_file, include_dependencies=True)
    
    prompt_parts = [
        f"Refactoring Goal: {refactoring_goal}",
        "",
        "Relevant Code Context:",
        context.to_prompt(),
    ]
    
    return "\n".join(prompt_parts)
