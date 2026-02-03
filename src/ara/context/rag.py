"""
RAG (Retrieval-Augmented Generation) utilities for large file handling.

When files are too large to send to the LLM in full, we:
1. Chunk the file into smaller pieces
2. Use semantic search to find relevant chunks
3. Send only relevant context to the LLM
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import hashlib
import re

import structlog

logger = structlog.get_logger()


# Maximum characters per chunk (roughly 2000 tokens)
DEFAULT_CHUNK_SIZE = 8000
DEFAULT_CHUNK_OVERLAP = 500


@dataclass
class CodeChunk:
    """A chunk of code with metadata."""
    content: str
    start_line: int
    end_line: int
    filepath: str
    chunk_index: int
    chunk_hash: str
    
    # Semantic info extracted during chunking
    contains_functions: List[str] = None
    contains_classes: List[str] = None
    imports: List[str] = None


class CodeChunker:
    """
    Intelligent code chunker that respects code structure.
    
    Unlike naive text chunking, this chunker:
    - Keeps functions and classes intact when possible
    - Preserves context with overlap
    - Tracks what each chunk contains for better retrieval
    """
    
    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_file(self, filepath: str, content: str) -> List[CodeChunk]:
        """
        Chunk a Python file intelligently.
        
        Args:
            filepath: Path to the file
            content: File content
        
        Returns:
            List of CodeChunks
        """
        if len(content) <= self.chunk_size:
            # File is small enough to process whole
            return [self._create_chunk(filepath, content, 0, 0, len(content.splitlines()))]
        
        # Split into logical blocks (functions, classes, etc.)
        blocks = self._extract_blocks(content)
        
        # Group blocks into chunks
        chunks = []
        current_chunk = []
        current_size = 0
        start_line = 1
        
        for block_content, block_start, block_end in blocks:
            block_size = len(block_content)
            
            if current_size + block_size > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_content = "\n\n".join(c for c, _, _ in current_chunk)
                chunk_end = current_chunk[-1][2]
                chunks.append(self._create_chunk(
                    filepath, chunk_content, len(chunks), start_line, chunk_end
                ))
                
                # Start new chunk with overlap
                if self.chunk_overlap > 0 and len(current_chunk) > 0:
                    # Keep last block for overlap
                    overlap_blocks = [current_chunk[-1]]
                    current_chunk = overlap_blocks
                    current_size = sum(len(c) for c, _, _ in overlap_blocks)
                    start_line = overlap_blocks[0][1]
                else:
                    current_chunk = []
                    current_size = 0
                    start_line = block_start
            
            current_chunk.append((block_content, block_start, block_end))
            current_size += block_size
        
        # Don't forget the last chunk
        if current_chunk:
            chunk_content = "\n\n".join(c for c, _, _ in current_chunk)
            chunk_end = current_chunk[-1][2]
            chunks.append(self._create_chunk(
                filepath, chunk_content, len(chunks), start_line, chunk_end
            ))
        
        logger.info("file_chunked", filepath=filepath, chunks=len(chunks))
        return chunks
    
    def _extract_blocks(self, content: str) -> List[Tuple[str, int, int]]:
        """
        Extract logical blocks from Python code.
        
        Returns list of (content, start_line, end_line) tuples.
        """
        lines = content.splitlines(keepends=True)
        blocks = []
        current_block = []
        current_start = 1
        in_definition = False
        
        for i, line in enumerate(lines, start=1):
            stripped = line.lstrip()
            
            # Check if this is a definition start
            is_def_start = (
                stripped.startswith("def ") or 
                stripped.startswith("async def ") or
                stripped.startswith("class ")
            )
            
            if is_def_start and current_block:
                # Save previous block
                block_content = "".join(current_block)
                blocks.append((block_content, current_start, i - 1))
                current_block = []
                current_start = i
            
            current_block.append(line)
        
        # Don't forget the last block
        if current_block:
            block_content = "".join(current_block)
            blocks.append((block_content, current_start, len(lines)))
        
        return blocks
    
    def _create_chunk(
        self,
        filepath: str,
        content: str,
        index: int,
        start_line: int,
        end_line: int,
    ) -> CodeChunk:
        """Create a CodeChunk with extracted metadata."""
        # Extract contained functions/classes
        functions = re.findall(r'def\s+(\w+)\s*\(', content)
        classes = re.findall(r'class\s+(\w+)\s*[:\(]', content)
        imports = re.findall(r'(?:from\s+(\S+)\s+)?import\s+(\S+)', content)
        import_list = [f"{i[0]}.{i[1]}" if i[0] else i[1] for i in imports]
        
        return CodeChunk(
            content=content,
            start_line=start_line,
            end_line=end_line,
            filepath=filepath,
            chunk_index=index,
            chunk_hash=hashlib.md5(content.encode()).hexdigest()[:8],
            contains_functions=functions,
            contains_classes=classes,
            imports=import_list,
        )


class ChunkRetriever:
    """
    Retrieves relevant chunks based on a query.
    
    Uses simple keyword matching. Could be upgraded to vector search.
    """
    
    def __init__(self, chunks: List[CodeChunk]):
        self.chunks = chunks
        self._build_index()
    
    def _build_index(self):
        """Build a simple keyword index."""
        self.keyword_index: Dict[str, List[int]] = {}
        
        for i, chunk in enumerate(self.chunks):
            # Index by function/class names
            for func in (chunk.contains_functions or []):
                self._add_to_index(func.lower(), i)
            for cls in (chunk.contains_classes or []):
                self._add_to_index(cls.lower(), i)
            for imp in (chunk.imports or []):
                self._add_to_index(imp.lower().split(".")[-1], i)
    
    def _add_to_index(self, keyword: str, chunk_idx: int):
        if keyword not in self.keyword_index:
            self.keyword_index[keyword] = []
        if chunk_idx not in self.keyword_index[keyword]:
            self.keyword_index[keyword].append(chunk_idx)
    
    def retrieve(self, query: str, top_k: int = 5) -> List[CodeChunk]:
        """
        Retrieve the most relevant chunks for a query.
        
        Args:
            query: Search query (keywords or description)
            top_k: Maximum chunks to return
        
        Returns:
            List of relevant CodeChunks
        """
        # Tokenize query
        query_words = set(query.lower().split())
        
        # Score each chunk by keyword overlap
        scores: Dict[int, int] = {}
        
        for word in query_words:
            # Check direct keyword matches
            if word in self.keyword_index:
                for chunk_idx in self.keyword_index[word]:
                    scores[chunk_idx] = scores.get(chunk_idx, 0) + 2
            
            # Check partial matches
            for keyword, chunk_indices in self.keyword_index.items():
                if word in keyword or keyword in word:
                    for chunk_idx in chunk_indices:
                        scores[chunk_idx] = scores.get(chunk_idx, 0) + 1
        
        # Sort by score and return top_k
        sorted_chunks = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        result = [self.chunks[idx] for idx, _ in sorted_chunks]
        
        # If no matches, return first few chunks
        if not result:
            result = self.chunks[:min(top_k, len(self.chunks))]
        
        logger.info("chunks_retrieved", query=query[:50], count=len(result))
        return result


def chunk_large_file(filepath: str, content: str) -> List[CodeChunk]:
    """Convenience function to chunk a large file."""
    chunker = CodeChunker()
    return chunker.chunk_file(filepath, content)


def retrieve_relevant_context(
    chunks: List[CodeChunk],
    goal: str,
    max_chunks: int = 3,
) -> str:
    """
    Get relevant context from chunks for a refactoring goal.
    
    Args:
        chunks: All chunks from the file
        goal: Refactoring goal description
        max_chunks: Maximum chunks to include
    
    Returns:
        Combined context string
    """
    retriever = ChunkRetriever(chunks)
    relevant = retriever.retrieve(goal, top_k=max_chunks)
    
    context_parts = []
    for chunk in relevant:
        header = f"# Lines {chunk.start_line}-{chunk.end_line}"
        if chunk.contains_functions:
            header += f" (functions: {', '.join(chunk.contains_functions)})"
        context_parts.append(f"{header}\n{chunk.content}")
    
    return "\n\n---\n\n".join(context_parts)
