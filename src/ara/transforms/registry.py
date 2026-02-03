"""
Transformer Registry - Central registry for all LibCST transformers.

Allows looking up transformers by name and creating them with configuration.
"""

from typing import Dict, Type, Any, Optional, List

import structlog

from ara.transforms.base import BaseTransformer, apply_transformer, TransformResult
from ara.transforms.rename import RenameFunctionTransformer, RenameMethodTransformer
from ara.transforms.type_hints import AddTypeHintTransformer, AddTypeHintFromDocstringTransformer
from ara.transforms.deprecated_api import DeprecatedAPIReplacer, SimplePatternReplacer

logger = structlog.get_logger()


# Registry of available transformers
TRANSFORMER_REGISTRY: Dict[str, Type[BaseTransformer]] = {
    "rename_function": RenameFunctionTransformer,
    "rename_method": RenameMethodTransformer,
    "add_type_hints": AddTypeHintTransformer,
    "add_type_hints_from_docstring": AddTypeHintFromDocstringTransformer,
    "replace_deprecated_api": DeprecatedAPIReplacer,
    "simple_pattern_replace": SimplePatternReplacer,
}


def get_transformer(
    name: str,
    **kwargs,
) -> BaseTransformer:
    """
    Get a transformer instance by name.
    
    Args:
        name: Name of the transformer (from registry)
        **kwargs: Arguments to pass to the transformer constructor
    
    Returns:
        Configured transformer instance
    
    Raises:
        ValueError: If transformer name not found
    """
    if name not in TRANSFORMER_REGISTRY:
        available = ", ".join(TRANSFORMER_REGISTRY.keys())
        raise ValueError(f"Unknown transformer: {name}. Available: {available}")
    
    transformer_class = TRANSFORMER_REGISTRY[name]
    return transformer_class(**kwargs)


def apply_transform(
    source_code: str,
    transformer_name: str,
    **kwargs,
) -> TransformResult:
    """
    Convenience function to apply a named transformer to source code.
    
    Args:
        source_code: Python source code to transform
        transformer_name: Name of the transformer (from registry)
        **kwargs: Arguments for the transformer
    
    Returns:
        TransformResult with original and modified code
    """
    transformer = get_transformer(transformer_name, **kwargs)
    return apply_transformer(source_code, transformer)


def apply_transforms_chain(
    source_code: str,
    transforms: List[Dict[str, Any]],
) -> TransformResult:
    """
    Apply a chain of transformers in sequence.
    
    Args:
        source_code: Python source code
        transforms: List of transform configs, each with:
                   {"name": "transformer_name", "kwargs": {...}}
    
    Returns:
        TransformResult with accumulated changes
    """
    current_code = source_code
    total_changes = 0
    all_descriptions = []
    
    for transform in transforms:
        name = transform["name"]
        kwargs = transform.get("kwargs", {})
        
        result = apply_transform(current_code, name, **kwargs)
        
        current_code = result.modified_code
        total_changes += result.changes_made
        all_descriptions.extend(result.change_descriptions)
    
    return TransformResult(
        original_code=source_code,
        modified_code=current_code,
        changes_made=total_changes,
        change_descriptions=all_descriptions,
    )


def list_available_transformers() -> List[str]:
    """Get a list of all available transformer names."""
    return list(TRANSFORMER_REGISTRY.keys())


def register_transformer(name: str, transformer_class: Type[BaseTransformer]):
    """
    Register a new transformer in the registry.
    
    Args:
        name: Name to register the transformer under
        transformer_class: The transformer class
    """
    TRANSFORMER_REGISTRY[name] = transformer_class
    logger.info("transformer_registered", name=name)
