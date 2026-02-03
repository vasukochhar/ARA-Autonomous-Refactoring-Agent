"""
LibCST Transformer Base - Common utilities for code transformers.

Provides base classes and utilities for building LibCST-based
code transformers that preserve formatting and comments.
"""

from abc import ABC, abstractmethod
from typing import Optional, Set, Dict, Any
from dataclasses import dataclass, field

import libcst as cst
from libcst import matchers as m
import structlog

logger = structlog.get_logger()


@dataclass
class TransformResult:
    """Result of a code transformation."""
    
    original_code: str
    modified_code: str
    changes_made: int = 0
    change_descriptions: list = field(default_factory=list)
    
    @property
    def has_changes(self) -> bool:
        return self.original_code != self.modified_code


class BaseTransformer(cst.CSTTransformer, ABC):
    """
    Base class for all ARA code transformers.
    
    Provides common functionality like change tracking and metadata access.
    """
    
    def __init__(self):
        super().__init__()
        self.changes_made = 0
        self.change_descriptions = []
    
    def record_change(self, description: str):
        """Record a change made by the transformer."""
        self.changes_made += 1
        self.change_descriptions.append(description)
        logger.debug("change_recorded", description=description)
    
    @abstractmethod
    def get_transformer_name(self) -> str:
        """Return the name of this transformer."""
        pass


def apply_transformer(
    source_code: str,
    transformer: BaseTransformer,
) -> TransformResult:
    """
    Apply a LibCST transformer to source code.
    
    Args:
        source_code: Python source code to transform
        transformer: Configured transformer instance
    
    Returns:
        TransformResult with original, modified code and change info
    """
    try:
        # Parse the source code
        tree = cst.parse_module(source_code)
        
        # Apply the transformer
        modified_tree = tree.visit(transformer)
        
        # Generate the modified code
        modified_code = modified_tree.code
        
        return TransformResult(
            original_code=source_code,
            modified_code=modified_code,
            changes_made=transformer.changes_made,
            change_descriptions=transformer.change_descriptions,
        )
        
    except Exception as e:
        logger.error("transform_failed", error=str(e))
        raise


def parse_module_safe(source_code: str) -> Optional[cst.Module]:
    """
    Safely parse Python source code into a CST module.
    
    Args:
        source_code: Python source code
    
    Returns:
        Parsed CST module or None if parsing fails
    """
    try:
        return cst.parse_module(source_code)
    except Exception as e:
        logger.warning("parse_failed", error=str(e))
        return None
