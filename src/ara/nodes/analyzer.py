"""
Analyzer Node - The Planner.

This node scans the codebase to identify refactoring targets and map dependencies.
It uses file system tools and optional LibCST parsing to identify patterns.
"""

from pathlib import Path
from typing import List, Optional

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ara.state.schema import AgentState
from ara.state.models import FileContext, FileStatus, RefactoringTarget
from ara.tools.file_ops import read_file, list_files
from ara.llm.provider import get_llm
from ara.context.dependency_graph import (
    build_dependency_graph, 
    build_symbol_table, 
    get_refactoring_order,
    DependencyGraph,
    SymbolResolver,
)

logger = structlog.get_logger()


class AnalysisResult(BaseModel):
    """Structured output from the analyzer."""
    
    targets: List[RefactoringTarget] = Field(
        default_factory=list,
        description="List of identified refactoring targets"
    )
    summary: str = Field(
        description="Summary of the analysis"
    )


ANALYZER_SYSTEM_PROMPT = """You are a code analysis expert. Your task is to analyze Python source code and identify specific refactoring targets based on the user's goal.

For each target you identify, provide:
1. The file path
2. The type of code element (function, class, method, import, etc.)
3. The name of the element
4. The line numbers (start and end)
5. A description of what needs to be changed

Be thorough but focused. Only identify targets that are relevant to the refactoring goal.
Return your analysis as structured JSON."""


def analyzer_node(state: AgentState) -> dict:
    """
    Analyze the codebase to identify refactoring targets.

    MULTI-FILE SUPPORT:
    1. Builds dependency graph for all files
    2. Determines processing order (leaves first)
    3. Sets up file queue for sequential processing

    Args:
        state: Current agent state

    Returns:
        Updated state with files, targets, dependency graph, and file queue
    """
    logger.info("analyzer_start", goal=state.get("refactoring_goal"))

    refactoring_goal = state.get("refactoring_goal", "")
    files_dict = state.get("files", {})

    # If no files provided, return with error
    if not files_dict:
        logger.warning("no_files_to_analyze")
        return {
            "error_state": "No files provided for analysis",
            "refactoring_targets": [],
        }

    # Get file contents for dependency analysis
    file_contents = {}
    for filepath, file_ctx in files_dict.items():
        if isinstance(file_ctx, FileContext):
            content = file_ctx.original_content
        else:
            content = file_ctx.get("original_content", "")
        file_contents[filepath] = content

    # BUILD DEPENDENCY GRAPH
    dependency_graph = build_dependency_graph(file_contents)
    logger.info(
        "dependency_graph_built_in_analyzer",
        modules=len(dependency_graph.modules),
        edges=len(dependency_graph.edges),
    )

    # BUILD SYMBOL TABLE for cross-file resolution
    symbol_table = build_symbol_table(file_contents)
    
    # DETERMINE PROCESSING ORDER
    all_files = list(files_dict.keys())
    file_queue = get_refactoring_order(dependency_graph, all_files)
    logger.info("file_queue_created", order=file_queue)

    # Set the first file to process
    current_file = file_queue[0] if file_queue else None

    # Collect combined content for LLM analysis
    combined_content = "\n".join(
        f"=== {fp} ===\n{content}\n" 
        for fp, content in file_contents.items()
    )

    # Use LLM to analyze and identify targets
    try:
        llm = get_llm(temperature=0.0)

        messages = [
            SystemMessage(content=ANALYZER_SYSTEM_PROMPT),
            HumanMessage(content=f"""Refactoring Goal: {refactoring_goal}

Source Code:
{combined_content}

Identify all code elements that need to be modified to achieve this goal.
For each target, provide the file path, element type, name, line numbers, and what needs to change.""")
        ]

        response = llm.invoke(messages)
        analysis_text = response.content

        logger.info("analyzer_complete", response_length=len(analysis_text))

        # Parse targets from the response
        targets = []

        return {
            "current_file_path": current_file,
            "file_queue": file_queue,
            "file_queue_index": 0,
            "refactoring_targets": targets,
            "human_feedback": f"Analysis complete: {analysis_text[:500]}...",
        }

    except Exception as e:
        logger.error("analyzer_error", error=str(e))
        
        # FALLBACK: Even on error, set current_file_path so generator can work
        logger.warning("analyzer_using_fallback", first_file=current_file, reason=str(e))
        
        return {
            "current_file_path": current_file,
            "file_queue": file_queue,
            "file_queue_index": 0,
            "refactoring_targets": [],
            "human_feedback": f"Analysis fallback (LLM unavailable): Processing {current_file}",
        }


def load_files_for_analysis(
    directory: str,
    pattern: str = "*.py",
    exclude_patterns: Optional[List[str]] = None,
) -> dict:
    """
    Load files from a directory into FileContext objects.

    Args:
        directory: Directory to scan
        pattern: Glob pattern for files
        exclude_patterns: Patterns to exclude

    Returns:
        Dictionary of filepath -> FileContext
    """
    exclude_patterns = exclude_patterns or [
        "__pycache__", ".git", "node_modules", ".venv", "venv", "test_"
    ]

    files_dict = {}
    
    try:
        file_list = list_files.invoke({
            "directory": directory,
            "pattern": pattern,
            "recursive": True,
            "exclude_patterns": exclude_patterns,
        })

        for filepath in file_list:
            try:
                content = read_file.invoke({"filepath": filepath})
                files_dict[filepath] = FileContext(
                    filepath=filepath,
                    original_content=content,
                    status=FileStatus.PENDING,
                )
            except Exception as e:
                logger.warning("file_read_error", filepath=filepath, error=str(e))

        logger.info("files_loaded", count=len(files_dict))
        return files_dict

    except Exception as e:
        logger.error("load_files_error", error=str(e))
        return {}
