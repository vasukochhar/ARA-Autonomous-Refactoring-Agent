
import os
import sys
from typing import List, Optional, Any
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult, ChatGeneration

# Custom Mock Implementation
class MockAraLLM(BaseChatModel):
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_msg = messages[-1].content
        print(f"DEBUG: Input message: {last_msg[:100]}...")
        
        response_content = "Mock response"
        
        # 1. Analyzer Response
        if "Refactoring Goal" in str(last_msg) and "Identify all code elements" in str(last_msg):
            response_content = """
            [
                {
                    "filepath": "user_stats.py",
                    "node_type": "function",
                    "node_name": "process_user_data",
                    "start_line": 1,
                    "end_line": 15,
                    "description": "Add type hints and improve variable names"
                }
            ]
            """
        
        # 2. Generator Response
        elif "Refactoring Goal" in str(last_msg) and "Generate the refactored code" in str(last_msg):
            response_content = '''```python
from typing import List, Dict, Any, Union

def process_user_data(users: List[Dict[str, Any]]) -> Dict[str, Union[int, float]]:
    """
    Process user data and return stats.
    """
    total_user_age = 0
    valid_user_list = []
    
    for user in users:
        if user.get('age') and user.get('name'):
            total_user_age += user['age']
            valid_user_list.append(user)
            
    average_age = total_user_age / len(valid_user_list) if valid_user_list else 0
    return {"count": len(valid_user_list), "average_age": average_age}
```'''
        
        # 3. Reflector Response
        elif "feedback" in str(last_msg).lower():
            response_content = "The code looks good but could use more docstrings."
            
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=response_content))])

    @property
    def _llm_type(self) -> str:
        return "mock-ara-llm"

# Test it
try:
    print("Initializing Mock LLM...")
    llm = MockAraLLM()
    print("Testing Analyzer invocation...")
    res = llm.invoke("Refactoring Goal: test\nIdentify all code elements needs to be modified...")
    print(f"Response: {res.content[:50]}")
    print("Success!")
except Exception as e:
    print(f"Failed: {e}")
    import traceback
    traceback.print_exc()
