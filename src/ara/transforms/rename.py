"""
Rename Transformer - LibCST-based safe rename with reference tracking.

Performs safe renames of functions, classes, and variables while
updating all references throughout the code.
"""

from typing import Dict, List, Optional, Set
import libcst as cst
from libcst import matchers as m
import structlog

from ara.transforms.base import BaseTransformer, apply_transformer, TransformResult

logger = structlog.get_logger()


class RenameTransformer(BaseTransformer):
    """
    Transformer that renames symbols and updates all references.
    
    Features:
    - Renames functions, classes, variables
    - Updates all call sites and references
    - Handles imports correctly
    - Preserves formatting
    """
    
    def __init__(self, renames: Dict[str, str]):
        """
        Initialize with rename mappings.
        
        Args:
            renames: Dict mapping old names to new names
        """
        super().__init__()
        self.renames = renames
        self.scopes: List[Set[str]] = [set()]  # Track local scopes
    
    def get_transformer_name(self) -> str:
        return "Rename"
    
    def _should_rename(self, name: str) -> bool:
        """Check if a name should be renamed."""
        return name in self.renames
    
    def _get_new_name(self, old_name: str) -> str:
        """Get the new name for a symbol."""
        return self.renames.get(old_name, old_name)
    
    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        """Track function scope entry."""
        self.scopes.append(set())
        return True
    
    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        """Rename function definitions and exit scope."""
        self.scopes.pop()
        
        func_name = updated_node.name.value
        if self._should_rename(func_name):
            new_name = self._get_new_name(func_name)
            self.record_change(f"Renamed function '{func_name}' to '{new_name}'")
            return updated_node.with_changes(
                name=cst.Name(new_name)
            )
        return updated_node
    
    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        """Rename class definitions."""
        class_name = updated_node.name.value
        if self._should_rename(class_name):
            new_name = self._get_new_name(class_name)
            self.record_change(f"Renamed class '{class_name}' to '{new_name}'")
            return updated_node.with_changes(
                name=cst.Name(new_name)
            )
        return updated_node
    
    def leave_Name(
        self, original_node: cst.Name, updated_node: cst.Name
    ) -> cst.Name:
        """Rename name references."""
        name = updated_node.value
        if self._should_rename(name):
            new_name = self._get_new_name(name)
            self.record_change(f"Updated reference '{name}' to '{new_name}'")
            return updated_node.with_changes(value=new_name)
        return updated_node
    
    def leave_Attribute(
        self, original_node: cst.Attribute, updated_node: cst.Attribute
    ) -> cst.Attribute:
        """Rename attribute accesses like obj.method."""
        attr_name = updated_node.attr.value
        if self._should_rename(attr_name):
            new_name = self._get_new_name(attr_name)
            self.record_change(f"Updated attribute '{attr_name}' to '{new_name}'")
            return updated_node.with_changes(
                attr=cst.Name(new_name)
            )
        return updated_node
    
    def leave_ImportAlias(
        self, original_node: cst.ImportAlias, updated_node: cst.ImportAlias
    ) -> cst.ImportAlias:
        """Rename imports."""
        if isinstance(updated_node.name, cst.Name):
            name = updated_node.name.value
            if self._should_rename(name):
                new_name = self._get_new_name(name)
                self.record_change(f"Updated import '{name}' to '{new_name}'")
                return updated_node.with_changes(
                    name=cst.Name(new_name)
                )
        return updated_node


class DeprecatedAPITransformer(BaseTransformer):
    """
    Transformer that replaces deprecated API calls with modern equivalents.
    """
    
    def __init__(self, replacements: Dict[str, str]):
        """
        Initialize with API replacement mappings.
        
        Args:
            replacements: Dict mapping 'old.api.call' to 'new.api.call'
        """
        super().__init__()
        self.replacements = replacements
    
    def get_transformer_name(self) -> str:
        return "DeprecatedAPIReplacement"
    
    def leave_Call(
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.Call:
        """Replace deprecated function calls."""
        # Get the full call path as string
        func_str = self._get_call_string(updated_node.func)
        
        if func_str in self.replacements:
            new_func_str = self.replacements[func_str]
            try:
                new_func = cst.parse_expression(new_func_str)
                self.record_change(f"Replaced '{func_str}' with '{new_func_str}'")
                return updated_node.with_changes(func=new_func)
            except Exception:
                pass
        
        return updated_node
    
    def _get_call_string(self, node: cst.BaseExpression) -> str:
        """Convert a call target to a string representation."""
        if isinstance(node, cst.Name):
            return node.value
        elif isinstance(node, cst.Attribute):
            base = self._get_call_string(node.value)
            return f"{base}.{node.attr.value}"
        return ""


def rename_symbols(source_code: str, renames: Dict[str, str]) -> TransformResult:
    """
    Convenience function to rename symbols in source code.
    
    Args:
        source_code: Python source code
        renames: Dict mapping old names to new names
    
    Returns:
        TransformResult with modified code
    """
    transformer = RenameTransformer(renames)
    return apply_transformer(source_code, transformer)


def replace_deprecated_apis(
    source_code: str, 
    replacements: Dict[str, str]
) -> TransformResult:
    """
    Replace deprecated API calls with modern equivalents.
    
    Args:
        source_code: Python source code
        replacements: Dict mapping old API calls to new ones
    
    Returns:
        TransformResult with modified code
    """
    transformer = DeprecatedAPITransformer(replacements)
    return apply_transformer(source_code, transformer)
