"""Transforms module - LibCST code transformers."""

from ara.transforms.base import (
    BaseTransformer,
    TransformResult,
    apply_transformer,
    parse_module_safe,
)
from ara.transforms.rename import (
    RenameFunctionTransformer,
    RenameMethodTransformer,
)
from ara.transforms.type_hints import (
    AddTypeHintTransformer,
    AddTypeHintFromDocstringTransformer,
)
from ara.transforms.deprecated_api import (
    DeprecatedAPIReplacer,
    APIReplacement,
    SimplePatternReplacer,
)
from ara.transforms.registry import (
    get_transformer,
    apply_transform,
    apply_transforms_chain,
    list_available_transformers,
    register_transformer,
)

__all__ = [
    # Base
    "BaseTransformer",
    "TransformResult",
    "apply_transformer",
    "parse_module_safe",
    # Rename
    "RenameFunctionTransformer",
    "RenameMethodTransformer",
    # Type Hints
    "AddTypeHintTransformer",
    "AddTypeHintFromDocstringTransformer",
    # Deprecated API
    "DeprecatedAPIReplacer",
    "APIReplacement",
    "SimplePatternReplacer",
    # Registry
    "get_transformer",
    "apply_transform",
    "apply_transforms_chain",
    "list_available_transformers",
    "register_transformer",
]
