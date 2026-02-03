"""
RenameFunction Transformer - Rename functions across a codebase.

Handles renaming of function definitions and all call sites.
"""

from typing import Set, Optional

import libcst as cst
from libcst import matchers as m
import structlog

from ara.transforms.base import BaseTransformer

logger = structlog.get_logger()


class RenameFunctionTransformer(BaseTransformer):
    """
    Transformer to rename a function and update all call sites.
    
    Handles:
    - Function definitions (def old_name -> def new_name)
    - Function calls (old_name() -> new_name())
    - Method definitions in classes
    - Does NOT rename method calls on objects (obj.old_name())
    """
    
    def __init__(self, old_name: str, new_name: str):
        super().__init__()
        self.old_name = old_name
        self.new_name = new_name
        self._in_class = False
    
    def get_transformer_name(self) -> str:
        return f"RenameFunction({self.old_name} -> {self.new_name})"
    
    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        """Track when we enter a class definition."""
        self._in_class = True
        return True
    
    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        """Track when we leave a class definition."""
        self._in_class = False
        return updated_node
    
    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        """Rename function definitions."""
        if original_node.name.value == self.old_name:
            new_name_node = cst.Name(self.new_name)
            context = "method" if self._in_class else "function"
            self.record_change(f"Renamed {context} '{self.old_name}' to '{self.new_name}'")
            return updated_node.with_changes(name=new_name_node)
        return updated_node
    
    def leave_Call(
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.Call:
        """Rename function calls (but not method calls on objects)."""
        # Check if it's a simple name call (not attribute access)
        if isinstance(original_node.func, cst.Name):
            if original_node.func.value == self.old_name:
                new_func = cst.Name(self.new_name)
                self.record_change(f"Updated call from '{self.old_name}()' to '{self.new_name}()'")
                return updated_node.with_changes(func=new_func)
        return updated_node


class RenameMethodTransformer(BaseTransformer):
    """
    Transformer to rename a method on a specific class/object.
    
    Handles:
    - Method definitions within a specific class
    - Method calls on instances (obj.old_name() -> obj.new_name())
    """
    
    def __init__(
        self,
        old_name: str,
        new_name: str,
        class_name: Optional[str] = None,
    ):
        super().__init__()
        self.old_name = old_name
        self.new_name = new_name
        self.class_name = class_name
        self._current_class: Optional[str] = None
    
    def get_transformer_name(self) -> str:
        if self.class_name:
            return f"RenameMethod({self.class_name}.{self.old_name} -> {self.new_name})"
        return f"RenameMethod(*.{self.old_name} -> {self.new_name})"
    
    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        """Track the current class we're in."""
        self._current_class = node.name.value
        return True
    
    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        """Leave class tracking."""
        self._current_class = None
        return updated_node
    
    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        """Rename method definitions in the target class."""
        if original_node.name.value == self.old_name:
            # Check if we're in the right class (or no class specified)
            if self.class_name is None or self._current_class == self.class_name:
                new_name_node = cst.Name(self.new_name)
                self.record_change(
                    f"Renamed method '{self.old_name}' to '{self.new_name}' "
                    f"in class '{self._current_class}'"
                )
                return updated_node.with_changes(name=new_name_node)
        return updated_node
    
    def leave_Attribute(
        self, original_node: cst.Attribute, updated_node: cst.Attribute
    ) -> cst.Attribute:
        """Rename method calls (obj.old_name -> obj.new_name)."""
        if original_node.attr.value == self.old_name:
            # We can't easily determine the class of 'obj' without type info
            # So we rename all attribute accesses with the old name
            if self.class_name is None:  # Only if no specific class targeted
                new_attr = cst.Name(self.new_name)
                self.record_change(
                    f"Updated attribute access '.{self.old_name}' to '.{self.new_name}'"
                )
                return updated_node.with_changes(attr=new_attr)
        return updated_node
