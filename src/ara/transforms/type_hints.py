"""
Type Hints Transformer - LibCST-based transformer to add type annotations.

Adds type hints to function parameters and return types using LibCST
for lossless, formatting-preserving transformations.
"""

from typing import Dict, List, Optional, Set, Union
import libcst as cst
from libcst import matchers as m
import structlog

from ara.transforms.base import BaseTransformer, apply_transformer, TransformResult

logger = structlog.get_logger()


# Common type inference mappings
DEFAULT_TYPE_MAPPINGS = {
    # Common parameter names -> type hints
    "data": "Dict[str, Any]",
    "items": "List[Any]",
    "name": "str",
    "names": "List[str]",
    "value": "Any",
    "values": "List[Any]",
    "count": "int",
    "index": "int",
    "id": "int",
    "flag": "bool",
    "enabled": "bool",
    "active": "bool",
    "text": "str",
    "message": "str",
    "path": "str",
    "filepath": "str",
    "filename": "str",
    "result": "Any",
    "results": "List[Any]",
    "config": "Dict[str, Any]",
    "options": "Dict[str, Any]",
    "args": "Any",
    "kwargs": "Any",
}


class AddTypeHintsTransformer(BaseTransformer):
    """
    Transformer that adds type hints to function definitions.
    
    Features:
    - Infers types from parameter names using common patterns
    - Adds 'Any' as default when type cannot be inferred
    - Adds 'None' return type for empty returns
    - Preserves existing type hints
    - Adds required imports (typing module)
    """
    
    def __init__(
        self,
        type_mappings: Optional[Dict[str, str]] = None,
        add_return_types: bool = True,
        default_type: str = "Any",
    ):
        super().__init__()
        self.type_mappings = {**DEFAULT_TYPE_MAPPINGS, **(type_mappings or {})}
        self.add_return_types = add_return_types
        self.default_type = default_type
        self.needs_typing_import = False
        self.used_types: Set[str] = set()
    
    def get_transformer_name(self) -> str:
        return "AddTypeHints"
    
    def _infer_type(self, param_name: str) -> str:
        """Infer type hint from parameter name."""
        name_lower = param_name.lower()
        
        # Check direct mappings
        if name_lower in self.type_mappings:
            return self.type_mappings[name_lower]
        
        # Check patterns
        if name_lower.endswith("_list") or name_lower.endswith("s"):
            return "List[Any]"
        if name_lower.endswith("_dict") or name_lower.endswith("_map"):
            return "Dict[str, Any]"
        if name_lower.startswith("is_") or name_lower.startswith("has_"):
            return "bool"
        if name_lower.endswith("_count") or name_lower.endswith("_num"):
            return "int"
        if name_lower.endswith("_str") or name_lower.endswith("_name"):
            return "str"
        
        return self.default_type
    
    def _parse_type_annotation(self, type_str: str) -> cst.Annotation:
        """Parse a type string into a CST Annotation node."""
        self.needs_typing_import = True
        
        # Track used types for import generation
        for type_name in ["Any", "List", "Dict", "Optional", "Union", "Tuple", "Set"]:
            if type_name in type_str:
                self.used_types.add(type_name)
        
        # Parse the type expression
        try:
            expr = cst.parse_expression(type_str)
            return cst.Annotation(annotation=expr)
        except Exception:
            # Fallback to Any
            self.used_types.add("Any")
            return cst.Annotation(annotation=cst.Name("Any"))
    
    def leave_Param(
        self, original_node: cst.Param, updated_node: cst.Param
    ) -> cst.Param:
        """Add type hints to function parameters without annotations."""
        # Skip if already has annotation
        if updated_node.annotation is not None:
            return updated_node
        
        # Skip *args and **kwargs
        if updated_node.star:
            return updated_node
        
        # Get parameter name
        param_name = updated_node.name.value
        
        # Skip 'self' and 'cls'
        if param_name in ("self", "cls"):
            return updated_node
        
        # Infer type
        inferred_type = self._infer_type(param_name)
        annotation = self._parse_type_annotation(inferred_type)
        
        self.record_change(f"Added type hint '{inferred_type}' to parameter '{param_name}'")
        
        return updated_node.with_changes(annotation=annotation)
    
    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        """Add return type annotations to functions."""
        if not self.add_return_types:
            return updated_node
        
        # Skip if already has return annotation
        if updated_node.returns is not None:
            return updated_node
        
        func_name = updated_node.name.value
        
        # Analyze function body for return statements
        return_type = self._analyze_returns(updated_node.body)
        
        if return_type:
            annotation = self._parse_type_annotation(return_type)
            self.record_change(f"Added return type '{return_type}' to function '{func_name}'")
            return updated_node.with_changes(returns=annotation)
        
        return updated_node
    
    def _analyze_returns(self, body: cst.BaseSuite) -> Optional[str]:
        """Analyze function body to infer return type."""
        # Simple heuristic: check for return statements
        class ReturnFinder(cst.CSTVisitor):
            def __init__(self):
                self.has_return = False
                self.has_return_value = False
            
            def visit_Return(self, node: cst.Return):
                self.has_return = True
                if node.value is not None:
                    self.has_return_value = True
        
        finder = ReturnFinder()
        body.walk(finder)
        
        if not finder.has_return:
            return "None"
        elif finder.has_return and not finder.has_return_value:
            return "None"
        else:
            return "Any"  # Can't infer specific type
    
    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        """Add typing imports if needed."""
        if not self.needs_typing_import or not self.used_types:
            return updated_node
        
        # Check if typing is already imported
        has_typing_import = False
        for stmt in updated_node.body:
            if isinstance(stmt, cst.SimpleStatementLine):
                for item in stmt.body:
                    if isinstance(item, cst.ImportFrom):
                        if isinstance(item.module, cst.Attribute):
                            continue
                        if item.module and item.module.value == "typing":
                            has_typing_import = True
                            break
        
        if has_typing_import:
            return updated_node
        
        # Create the import statement
        types_to_import = sorted(self.used_types)
        import_names = [
            cst.ImportAlias(name=cst.Name(t)) for t in types_to_import
        ]
        
        new_import = cst.SimpleStatementLine(
            body=[
                cst.ImportFrom(
                    module=cst.Name("typing"),
                    names=import_names,
                )
            ]
        )
        
        # Add import at the beginning (after any __future__ imports)
        new_body = [new_import] + list(updated_node.body)
        
        self.record_change(f"Added 'from typing import {', '.join(types_to_import)}'")
        
        return updated_node.with_changes(body=new_body)


def add_type_hints(source_code: str, **kwargs) -> TransformResult:
    """
    Convenience function to add type hints to source code.
    
    Args:
        source_code: Python source code
        **kwargs: Additional arguments for AddTypeHintsTransformer
    
    Returns:
        TransformResult with modified code
    """
    transformer = AddTypeHintsTransformer(**kwargs)
    return apply_transformer(source_code, transformer)
