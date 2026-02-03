"""
End-to-end test script for ARA pipeline.
Tests the complete workflow with real Gemini LLM calls.
"""

import asyncio
import sys
sys.path.insert(0, 'd:/test/src')

from ara.state.schema import create_initial_state
from ara.state.models import FileContext
from ara.nodes.analyzer import analyzer_node
from ara.nodes.generator import generator_node
from ara.nodes.validator import validator_node


# Sample code to refactor
SAMPLE_CODE = '''
def calculate_area(width, height):
    """Calculate the area of a rectangle."""
    return width * height


def calculate_perimeter(width, height):
    """Calculate the perimeter of a rectangle."""
    return 2 * (width + height)


def process_data(data):
    """Process a list of data items."""
    result = []
    for item in data:
        result.append(item * 2)
    return result
'''


async def test_analyzer_node():
    """Test the analyzer node with real LLM."""
    print("=" * 60)
    print("TEST 1: Analyzer Node")
    print("=" * 60)
    
    state = create_initial_state(
        refactoring_goal="Add type hints to all functions",
        max_iterations=3,
    )
    state["files"] = {
        "sample.py": FileContext(
            filepath="sample.py",
            original_content=SAMPLE_CODE,
        )
    }
    
    result = analyzer_node(state)
    
    if result.get("error_state"):
        print(f"\n❌ NODE ERROR: {result['error_state']}")
        return {**state, **result}
    
    print(f"✓ Current file: {result.get('current_file_path')}")
    print(f"✓ Targets found: {len(result.get('refactoring_targets', []))}")
    print(f"✓ Feedback: {result.get('human_feedback', '')[:200]}...")
    
    return {**state, **result}


async def test_generator_node(state):
    """Test the generator node with real LLM."""
    print("\n" + "=" * 60)
    print("TEST 2: Generator Node")
    print("=" * 60)
    
    result = generator_node(state)
    
    generated = result.get("generated_code_snippet", "")
    print(f"✓ Generated {len(generated)} characters of code")
    print("\nGenerated code preview:")
    print("-" * 40)
    print(generated[:500] if generated else "No code generated")
    print("-" * 40)
    
    return {**state, **result}


async def test_validator_node(state):
    """Test the validator node."""
    print("\n" + "=" * 60)
    print("TEST 3: Validator Node")
    print("=" * 60)
    
    result = validator_node(state)
    
    validations = result.get("validation_history", [])
    print(f"✓ Ran {len(validations)} validation checks")
    
    for v in validations:
        icon = "✓" if v.passed else "✗"
        print(f"  {icon} {v.tool_name}: {'PASSED' if v.passed else 'FAILED'}")
        if not v.passed and v.error_message:
            print(f"      Error: {v.error_message[:100]}...")
    
    return {**state, **result}


async def test_full_pipeline():
    """Run the full pipeline end-to-end."""
    print("\n" + "=" * 60)
    print("ARA END-TO-END PIPELINE TEST")
    print("=" * 60)
    print(f"\nRefactoring goal: Add type hints to all functions")
    print(f"Sample code: {len(SAMPLE_CODE)} characters\n")
    
    try:
        # Step 1: Analyze
        state = await test_analyzer_node()
        
        if state.get("error_state"):
            print(f"\n❌ Analyzer error: {state['error_state']}")
            return False
        
        # Step 2: Generate
        state = await test_generator_node(state)
        
        if state.get("error_state"):
            print(f"\n❌ Generator error: {state['error_state']}")
            return False
        
        # Step 3: Validate
        state = await test_validator_node(state)
        
        # Check overall result
        validations = state.get("validation_history", [])
        all_passed = all(v.passed for v in validations)
        
        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        
        if all_passed:
            print("✓ All validations PASSED!")
            print("\nFinal refactored code:")
            print("-" * 40)
            print(state.get("generated_code_snippet", "No code")[:800])
            print("-" * 40)
        else:
            print("✗ Some validations FAILED")
            print("The reflector would now analyze failures and retry...")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse
    from unittest.mock import MagicMock
    from langchain_core.messages import AIMessage
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Mock LLM calls")
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("Starting ARA Pipeline E2E Test")
    if args.mock:
        print("Using MOCKED LLM (Checking pipeline logic only)")
        
        # Patch get_llm
        import ara.nodes.analyzer
        import ara.nodes.generator
        import ara.nodes.reflector
        
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="""
        [
            {
                "file_path": "sample.py",
                "element_type": "function",
                "name": "calculate_area",
                "line_start": 1,
                "line_end": 3,
                "description": "Add type hints"
            }
        ]
        """)
        
        # Make generator return valid python code to pass validation
        def mock_invoke(messages):
            content = messages[-1].content
            if "Refactoring Goal" in str(content):  # Analyzer
                return AIMessage(content='Target identified: calculate_area')
            elif "Task: Implement the following refactoring" in str(content): # Generator
                return AIMessage(content='''```python
def calculate_area(width: float, height: float) -> float:
    """Calculate the area of a rectangle."""
    return width * height

def calculate_perimeter(width, height):
    """Calculate the perimeter of a rectangle."""
    return 2 * (width + height)

def process_data(data):
    """Process a list of data items."""
    result = []
    for item in data:
        result.append(item * 2)
    return result
```''')
            return AIMessage(content="Analysis complete.")

        mock_llm.invoke.side_effect = mock_invoke
        
        # Apply patches
        ara.nodes.analyzer.get_llm = MagicMock(return_value=mock_llm)
        ara.nodes.generator.get_llm = MagicMock(return_value=mock_llm)
        ara.nodes.reflector.get_llm = MagicMock(return_value=mock_llm)
        
    else:
        print("Using REAL Gemini API calls")
    print("=" * 60 + "\n")
    
    asyncio.run(test_full_pipeline())

