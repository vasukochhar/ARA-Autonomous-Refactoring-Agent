"""
File system operations for ARA.

Provides LangChain-compatible tools for reading, writing, and listing files.
These tools are used by the agent nodes to interact with the codebase.
"""

import os
from pathlib import Path
from typing import List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class FileInfo(BaseModel):
    """Information about a file."""

    path: str
    name: str
    extension: str
    size_bytes: int
    is_file: bool
    is_directory: bool


@tool
def read_file(filepath: str) -> str:
    """
    Read the contents of a file.

    Args:
        filepath: Absolute or relative path to the file to read

    Returns:
        The file contents as a string

    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If the file cannot be read
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {filepath}")

    try:
        content = path.read_text(encoding="utf-8")
        logger.info("file_read", filepath=filepath, size=len(content))
        return content
    except UnicodeDecodeError:
        # Try with different encodings
        for encoding in ["latin-1", "cp1252"]:
            try:
                content = path.read_text(encoding=encoding)
                logger.warning(
                    "file_read_fallback_encoding",
                    filepath=filepath,
                    encoding=encoding,
                )
                return content
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Could not decode file with any supported encoding: {filepath}")


@tool
def write_file(filepath: str, content: str, create_dirs: bool = True) -> bool:
    """
    Write content to a file.

    Args:
        filepath: Absolute or relative path to the file to write
        content: The content to write to the file
        create_dirs: If True, create parent directories if they don't exist

    Returns:
        True if the file was written successfully

    Raises:
        PermissionError: If the file cannot be written
    """
    path = Path(filepath)

    if create_dirs and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("created_directories", path=str(path.parent))

    path.write_text(content, encoding="utf-8")
    logger.info("file_written", filepath=filepath, size=len(content))
    return True


@tool
def list_files(
    directory: str,
    pattern: str = "*.py",
    recursive: bool = True,
    exclude_patterns: Optional[List[str]] = None,
) -> List[str]:
    """
    List files in a directory matching a pattern.

    Args:
        directory: Path to the directory to search
        pattern: Glob pattern to match (default: "*.py")
        recursive: If True, search subdirectories recursively
        exclude_patterns: List of patterns to exclude (e.g., ["*test*", "__pycache__"])

    Returns:
        List of file paths matching the pattern
    """
    path = Path(directory)
    exclude_patterns = exclude_patterns or ["__pycache__", ".git", "node_modules", ".venv", "venv"]

    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {directory}")

    if recursive:
        files = list(path.rglob(pattern))
    else:
        files = list(path.glob(pattern))

    # Filter out excluded patterns
    result = []
    for file in files:
        file_str = str(file)
        excluded = False
        for exclude in exclude_patterns:
            if exclude in file_str:
                excluded = True
                break
        if not excluded:
            result.append(str(file))

    logger.info(
        "files_listed",
        directory=directory,
        pattern=pattern,
        count=len(result),
    )
    return result


@tool
def get_file_info(filepath: str) -> FileInfo:
    """
    Get information about a file.

    Args:
        filepath: Path to the file

    Returns:
        FileInfo object with file metadata
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"Path not found: {filepath}")

    return FileInfo(
        path=str(path.absolute()),
        name=path.name,
        extension=path.suffix,
        size_bytes=path.stat().st_size if path.is_file() else 0,
        is_file=path.is_file(),
        is_directory=path.is_dir(),
    )


def create_backup(filepath: str) -> str:
    """
    Create a backup of a file before modifying it.

    Args:
        filepath: Path to the file to backup

    Returns:
        Path to the backup file
    """
    path = Path(filepath)
    backup_path = path.with_suffix(path.suffix + ".bak")

    if path.exists():
        content = path.read_text(encoding="utf-8")
        backup_path.write_text(content, encoding="utf-8")
        logger.info("backup_created", original=filepath, backup=str(backup_path))

    return str(backup_path)


def generate_diff(original: str, modified: str, filepath: str = "file") -> str:
    """
    Generate a unified diff between original and modified content.

    Args:
        original: Original file content
        modified: Modified file content
        filepath: Filename for diff header

    Returns:
        Unified diff string
    """
    import difflib

    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        lineterm="",
    )

    return "".join(diff)
