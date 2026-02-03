"""Transforms module - LibCST code transformers for lossless refactoring."""

from ara.transforms.base import (
    BaseTransformer,
    TransformResult,
    apply_transformer,
    parse_module_safe,
)
from ara.transforms.type_hints import (
    AddTypeHintsTransformer,
    add_type_hints,
)
from ara.transforms.rename import (
    RenameTransformer,
    DeprecatedAPITransformer,
    rename_symbols,
    replace_deprecated_apis,
)
from ara.transforms.cleanup import (
    AddDocstringsTransformer,
    RemoveUnusedImportsTransformer,
    SafeDivisionTransformer,
    add_docstrings,
    remove_unused_imports,
)

__all__ = [
    # Base
    "BaseTransformer",
    "TransformResult",
    "apply_transformer",
    "parse_module_safe",
    # Type Hints
    "AddTypeHintsTransformer",
    "add_type_hints",
    # Rename
    "RenameTransformer",
    "DeprecatedAPITransformer",
    "rename_symbols",
    "replace_deprecated_apis",
    # Cleanup
    "AddDocstringsTransformer",
    "RemoveUnusedImportsTransformer",
    "SafeDivisionTransformer",
    "add_docstrings",
    "remove_unused_imports",
]


# Transform registry for dynamic selection
TRANSFORM_REGISTRY = {
    "add_type_hints": add_type_hints,
    "rename_symbols": rename_symbols,
    "replace_deprecated_apis": replace_deprecated_apis,
    "add_docstrings": add_docstrings,
    "remove_unused_imports": remove_unused_imports,
}


def get_transform(name: str):
    """Get a transform function by name."""
    return TRANSFORM_REGISTRY.get(name)


def list_transforms():
    """List available transform names."""
    return list(TRANSFORM_REGISTRY.keys())


def apply_transform_by_name(name: str, source_code: str, **kwargs) -> TransformResult:
    """Apply a transform by name."""
    transform_fn = get_transform(name)
    if not transform_fn:
        raise ValueError(f"Unknown transform: {name}")
    return transform_fn(source_code, **kwargs)
