"""
DeprecatedAPIReplacer Transformer - Replace deprecated API calls.

Handles mapping old API patterns to new ones while preserving semantics.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import libcst as cst
from libcst import matchers as m
import structlog

from ara.transforms.base import BaseTransformer

logger = structlog.get_logger()


@dataclass
class APIReplacement:
    """Definition for an API replacement."""
    
    old_name: str  # Old function/method name
    new_name: str  # New function/method name
    old_module: Optional[str] = None  # e.g., "os.path"
    new_module: Optional[str] = None  # e.g., "pathlib"
    argument_mapping: Optional[Dict[str, str]] = None  # Map old arg names to new
    wrapper_function: Optional[str] = None  # Wrap the call in this function


# Common deprecated API replacements
COMMON_REPLACEMENTS = [
    # typing.Optional -> X | None (Python 3.10+)
    APIReplacement(
        old_name="Optional",
        new_name="",  # Remove and use | None
        old_module="typing",
    ),
    # collections.Callable -> collections.abc.Callable
    APIReplacement(
        old_name="Callable",
        new_name="Callable",
        old_module="collections",
        new_module="collections.abc",
    ),
    # os.path.join -> pathlib.Path
    APIReplacement(
        old_name="join",
        new_name="/",  # Path uses / operator
        old_module="os.path",
        new_module="pathlib",
    ),
]


class DeprecatedAPIReplacer(BaseTransformer):
    """
    Transformer to replace deprecated API calls with modern alternatives.
    
    Handles:
    - Function/method renames
    - Module migrations
    - Argument reordering/renaming
    """
    
    def __init__(self, replacements: Optional[List[APIReplacement]] = None):
        """
        Initialize the deprecated API replacer.
        
        Args:
            replacements: List of API replacements to apply.
                         Uses COMMON_REPLACEMENTS if not specified.
        """
        super().__init__()
        self.replacements = replacements or []
        self._replacement_map = self._build_replacement_map()
    
    def get_transformer_name(self) -> str:
        return "DeprecatedAPIReplacer"
    
    def _build_replacement_map(self) -> Dict[str, APIReplacement]:
        """Build a lookup map for replacements."""
        return {r.old_name: r for r in self.replacements}
    
    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.ImportFrom:
        """Update imports for deprecated modules."""
        if original_node.module is None:
            return updated_node
        
        module_name = self._get_module_name(original_node.module)
        
        for replacement in self.replacements:
            if replacement.old_module and module_name == replacement.old_module:
                if replacement.new_module:
                    # Update the module
                    new_module = cst.parse_expression(replacement.new_module)
                    if isinstance(new_module, cst.Attribute):
                        self.record_change(
                            f"Updated import from '{replacement.old_module}' "
                            f"to '{replacement.new_module}'"
                        )
                        return updated_node.with_changes(module=new_module)
        
        return updated_node
    
    def leave_Call(
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.BaseExpression:
        """Replace deprecated function/method calls."""
        func_name = self._get_call_name(original_node.func)
        
        if func_name in self._replacement_map:
            replacement = self._replacement_map[func_name]
            
            # Simple name replacement
            if replacement.new_name and isinstance(original_node.func, cst.Name):
                new_func = cst.Name(replacement.new_name)
                self.record_change(
                    f"Replaced '{func_name}()' with '{replacement.new_name}()'"
                )
                return updated_node.with_changes(func=new_func)
            
            # Attribute replacement (obj.old_method -> obj.new_method)
            if replacement.new_name and isinstance(original_node.func, cst.Attribute):
                new_attr = cst.Name(replacement.new_name)
                new_func = original_node.func.with_changes(attr=new_attr)
                self.record_change(
                    f"Replaced '.{func_name}()' with '.{replacement.new_name}()'"
                )
                return updated_node.with_changes(func=new_func)
        
        return updated_node
    
    def _get_module_name(self, module: cst.BaseExpression) -> str:
        """Extract the full module name from an import."""
        if isinstance(module, cst.Name):
            return module.value
        elif isinstance(module, cst.Attribute):
            parts = []
            current = module
            while isinstance(current, cst.Attribute):
                parts.append(current.attr.value)
                current = current.value
            if isinstance(current, cst.Name):
                parts.append(current.value)
            return ".".join(reversed(parts))
        return ""
    
    def _get_call_name(self, func: cst.BaseExpression) -> str:
        """Extract the function name from a call."""
        if isinstance(func, cst.Name):
            return func.value
        elif isinstance(func, cst.Attribute):
            return func.attr.value
        return ""


class SimplePatternReplacer(BaseTransformer):
    """
    Simple pattern-based code replacer.
    
    Takes a dictionary of old_pattern -> new_pattern and replaces
    matching code patterns.
    """
    
    def __init__(self, patterns: Dict[str, str]):
        """
        Initialize the pattern replacer.
        
        Args:
            patterns: Dict mapping old patterns to new patterns.
                     Keys are old code patterns, values are replacements.
        """
        super().__init__()
        self.patterns = patterns
    
    def get_transformer_name(self) -> str:
        return "SimplePatternReplacer"
    
    def leave_Name(
        self, original_node: cst.Name, updated_node: cst.Name
    ) -> cst.Name:
        """Replace simple name patterns."""
        if original_node.value in self.patterns:
            new_value = self.patterns[original_node.value]
            self.record_change(
                f"Replaced '{original_node.value}' with '{new_value}'"
            )
            return cst.Name(new_value)
        return updated_node
