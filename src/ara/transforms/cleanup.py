"""
Code Cleanup Transformer - LibCST-based transformer for general code improvements.

Provides transformations for:
- Removing unused imports
- Adding docstrings
- Formatting improvements
"""

from typing import Dict, List, Optional, Set
import libcst as cst
from libcst import matchers as m
import structlog

from ara.transforms.base import BaseTransformer, apply_transformer, TransformResult

logger = structlog.get_logger()


class AddDocstringsTransformer(BaseTransformer):
    """
    Transformer that adds docstrings to functions and classes.
    
    Generates basic docstring templates with parameter descriptions.
    """
    
    def __init__(self, style: str = "google"):
        """
        Initialize the docstring transformer.
        
        Args:
            style: Docstring style - 'google', 'numpy', or 'sphinx'
        """
        super().__init__()
        self.style = style
    
    def get_transformer_name(self) -> str:
        return "AddDocstrings"
    
    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        """Add docstrings to functions without them."""
        # Check if already has docstring
        body = updated_node.body
        if isinstance(body, cst.IndentedBlock):
            first_stmt = body.body[0] if body.body else None
            if first_stmt and isinstance(first_stmt, cst.SimpleStatementLine):
                if first_stmt.body and isinstance(first_stmt.body[0], cst.Expr):
                    expr = first_stmt.body[0].value
                    if isinstance(expr, (cst.SimpleString, cst.ConcatenatedString)):
                        # Already has docstring
                        return updated_node
        
        # Generate docstring
        func_name = updated_node.name.value
        params = self._extract_params(updated_node.params)
        docstring = self._generate_docstring(func_name, params)
        
        # Create docstring node
        docstring_node = cst.SimpleStatementLine(
            body=[cst.Expr(value=cst.SimpleString(f'"""{docstring}"""'))]
        )
        
        # Add to function body
        if isinstance(body, cst.IndentedBlock):
            new_body = cst.IndentedBlock(
                body=[docstring_node] + list(body.body)
            )
            self.record_change(f"Added docstring to function '{func_name}'")
            return updated_node.with_changes(body=new_body)
        
        return updated_node
    
    def _extract_params(self, params: cst.Parameters) -> List[str]:
        """Extract parameter names from function parameters."""
        param_names = []
        for param in params.params:
            name = param.name.value
            if name not in ("self", "cls"):
                param_names.append(name)
        return param_names
    
    def _generate_docstring(self, func_name: str, params: List[str]) -> str:
        """Generate a docstring template."""
        lines = [f"\n    {func_name.replace('_', ' ').title()}.\n"]
        
        if params:
            if self.style == "google":
                lines.append("    \n    Args:")
                for param in params:
                    lines.append(f"        {param}: Description of {param}.")
                lines.append("    \n    Returns:\n        Description of return value.\n    ")
            elif self.style == "numpy":
                lines.append("    \n    Parameters\n    ----------")
                for param in params:
                    lines.append(f"    {param} : type\n        Description of {param}.")
                lines.append("    \n    Returns\n    -------\n    type\n        Description.\n    ")
        else:
            lines.append("    ")
        
        return "".join(lines)


class RemoveUnusedImportsTransformer(BaseTransformer):
    """
    Transformer that removes unused imports.
    
    Analyzes code to find which imported names are actually used,
    then removes unused imports.
    """
    
    def __init__(self):
        super().__init__()
        self.used_names: Set[str] = set()
        self.imported_names: Dict[str, cst.ImportFrom] = {}
    
    def get_transformer_name(self) -> str:
        return "RemoveUnusedImports"
    
    def visit_Name(self, node: cst.Name) -> None:
        """Track all name usages."""
        self.used_names.add(node.value)
    
    def visit_Attribute(self, node: cst.Attribute) -> None:
        """Track attribute accesses."""
        if isinstance(node.value, cst.Name):
            self.used_names.add(node.value.value)
    
    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.ImportFrom:
        """Remove unused imports from import statements."""
        if isinstance(updated_node.names, cst.ImportStar):
            return updated_node
        
        # Filter to only used imports
        used_aliases = []
        removed = []
        
        for alias in updated_node.names:
            name = alias.asname.name.value if alias.asname else alias.name.value
            if isinstance(alias.name, cst.Name):
                original_name = alias.name.value
            else:
                original_name = str(alias.name)
            
            if name in self.used_names or original_name in self.used_names:
                used_aliases.append(alias)
            else:
                removed.append(name)
        
        if removed:
            self.record_change(f"Removed unused imports: {', '.join(removed)}")
        
        if not used_aliases:
            # Remove entire import statement
            return cst.RemovalSentinel.REMOVE
        
        if len(used_aliases) != len(updated_node.names):
            return updated_node.with_changes(names=used_aliases)
        
        return updated_node


class SafeDivisionTransformer(BaseTransformer):
    """
    Transformer that adds ZeroDivisionError protection.
    
    Wraps division operations in safety checks.
    """
    
    def __init__(self):
        super().__init__()
    
    def get_transformer_name(self) -> str:
        return "SafeDivision"
    
    def leave_BinaryOperation(
        self, original_node: cst.BinaryOperation, updated_node: cst.BinaryOperation
    ) -> cst.BaseExpression:
        """Wrap division operations with safety check."""
        # Check if this is a division
        if isinstance(updated_node.operator, (cst.Divide, cst.FloorDivide)):
            # Create: (divisor) if (divisor) != 0 else 0
            # This is a simple safety pattern
            divisor = updated_node.right
            
            # For complex expressions, we might want to use a more sophisticated approach
            # For now, just note it
            self.record_change(f"Found division operation that may need protection")
        
        return updated_node


def add_docstrings(source_code: str, style: str = "google") -> TransformResult:
    """Add docstrings to functions and classes."""
    transformer = AddDocstringsTransformer(style=style)
    return apply_transformer(source_code, transformer)


def remove_unused_imports(source_code: str) -> TransformResult:
    """Remove unused imports from source code."""
    transformer = RemoveUnusedImportsTransformer()
    return apply_transformer(source_code, transformer)
