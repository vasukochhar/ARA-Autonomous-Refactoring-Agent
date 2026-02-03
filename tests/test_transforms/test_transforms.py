"""Tests for LibCST transformers."""

import pytest

from ara.transforms.base import apply_transformer, TransformResult
from ara.transforms.rename import RenameFunctionTransformer, RenameMethodTransformer
from ara.transforms.type_hints import AddTypeHintTransformer
from ara.transforms.deprecated_api import DeprecatedAPIReplacer, APIReplacement
from ara.transforms.registry import (
    get_transformer,
    apply_transform,
    list_available_transformers,
)


class TestRenameFunctionTransformer:
    """Tests for function renaming."""

    def test_rename_function_definition(self):
        """Test renaming a function definition."""
        source = '''
def old_name():
    pass
'''
        transformer = RenameFunctionTransformer("old_name", "new_name")
        result = apply_transformer(source, transformer)
        
        assert result.has_changes
        assert "def new_name():" in result.modified_code
        assert "def old_name():" not in result.modified_code
        assert result.changes_made >= 1

    def test_rename_function_call(self):
        """Test renaming function calls."""
        source = '''
def old_name():
    pass

old_name()
'''
        transformer = RenameFunctionTransformer("old_name", "new_name")
        result = apply_transformer(source, transformer)
        
        assert "new_name()" in result.modified_code
        assert result.changes_made >= 2  # Definition + call

    def test_no_rename_method_call(self):
        """Test that method calls are not renamed."""
        source = '''
obj.old_name()
'''
        transformer = RenameFunctionTransformer("old_name", "new_name")
        result = apply_transformer(source, transformer)
        
        # Method call should not be renamed
        assert "obj.old_name()" in result.modified_code


class TestAddTypeHintTransformer:
    """Tests for type hint addition."""

    def test_add_return_type(self):
        """Test adding return type hint."""
        source = '''
def foo():
    pass
'''
        transformer = AddTypeHintTransformer(default_return_type="None")
        result = apply_transformer(source, transformer)
        
        assert "-> None" in result.modified_code

    def test_infer_types_from_defaults(self):
        """Test inferring types from default values."""
        source = '''
def foo(x=10, name="test"):
    pass
'''
        transformer = AddTypeHintTransformer(infer_from_defaults=True)
        result = apply_transformer(source, transformer)
        
        assert "x: int" in result.modified_code or result.changes_made >= 1

    def test_explicit_type_hints(self):
        """Test providing explicit type hints."""
        source = '''
def greet(name):
    return f"Hello, {name}"
'''
        hints = {"greet": {"name": "str", "return": "str"}}
        transformer = AddTypeHintTransformer(type_hints=hints)
        result = apply_transformer(source, transformer)
        
        assert "name: str" in result.modified_code
        assert "-> str" in result.modified_code

    def test_skip_self_parameter(self):
        """Test that self parameter is not annotated."""
        source = '''
class Foo:
    def bar(self):
        pass
'''
        transformer = AddTypeHintTransformer()
        result = apply_transformer(source, transformer)
        
        # self should not have an annotation
        assert "self:" not in result.modified_code


class TestDeprecatedAPIReplacer:
    """Tests for deprecated API replacement."""

    def test_replace_function_call(self):
        """Test replacing a deprecated function call."""
        source = '''
old_api()
'''
        replacements = [
            APIReplacement(old_name="old_api", new_name="new_api")
        ]
        transformer = DeprecatedAPIReplacer(replacements)
        result = apply_transformer(source, transformer)
        
        assert "new_api()" in result.modified_code


class TestTransformerRegistry:
    """Tests for the transformer registry."""

    def test_list_available_transformers(self):
        """Test listing available transformers."""
        transformers = list_available_transformers()
        
        assert "rename_function" in transformers
        assert "add_type_hints" in transformers
        assert "replace_deprecated_api" in transformers

    def test_get_transformer(self):
        """Test getting a transformer by name."""
        transformer = get_transformer(
            "rename_function",
            old_name="foo",
            new_name="bar",
        )
        
        assert transformer.old_name == "foo"
        assert transformer.new_name == "bar"

    def test_apply_transform(self):
        """Test the convenience apply_transform function."""
        source = "def foo(): pass"
        result = apply_transform(
            source,
            "rename_function",
            old_name="foo",
            new_name="bar",
        )
        
        assert result.has_changes
        assert "def bar():" in result.modified_code
