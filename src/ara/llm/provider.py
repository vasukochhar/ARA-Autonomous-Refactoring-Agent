"""
LLM provider configuration for ARA.

Provides a unified interface to create LLM instances using Gemini.
"""

from typing import Optional

import structlog
from langchain_core.language_models import BaseChatModel

from ara.config import get_settings

logger = structlog.get_logger()


def get_llm(
    model: Optional[str] = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """
    Get an LLM instance configured with Gemini.

    Args:
        model: Model name override (default from settings)
        temperature: Temperature for generation (0.0 = deterministic)

    Returns:
        Configured LangChain chat model
    """
    settings = get_settings()
    
    # Check for Mock Mode
    import os
    if os.environ.get("MOCK_LLM") == "true":
        logger.warning("llm_using_mock_mode")
        from typing import List, Optional, Any
        from langchain_core.language_models import BaseChatModel
        from langchain_core.messages import AIMessage, BaseMessage
        from langchain_core.outputs import ChatResult, ChatGeneration
        
        class MockAraLLM(BaseChatModel):
            def _generate(
                self,
                messages: List[BaseMessage],
                stop: Optional[List[str]] = None,
                run_manager: Any = None,
                **kwargs: Any,
            ) -> ChatResult:
                last_msg = messages[-1].content
                # logger.info("mock_llm_invoke", input_preview=last_msg[:100])
                # Debug logging removed for production
                
                response_content = "Mock response"
                
                msg_lower = last_msg.lower()
                
                # 1. Analyzer Response
                if "identify" in msg_lower:
                    if "calculate_metrics" in msg_lower or "process_data" in msg_lower:
                        print("DEBUGGING: Matched ANALYZER (User Content)")
                        response_content = """
                        {
                            "refactoring_targets": [
                                {
                                    "filepath": "legacy_processor.py",
                                    "node_type": "function",
                                    "node_name": "calculate_metrics",
                                    "start_line": 1,
                                    "end_line": 15,
                                    "description": "Add type hints and fix ZeroDivisionError"
                                },
                                {
                                    "filepath": "legacy_processor.py",
                                    "node_type": "function",
                                    "node_name": "process_data",
                                    "start_line": 17,
                                    "end_line": 26,
                                    "description": "Add type hints"
                                }
                            ]
                        }
                        """
                    else:
                        print("DEBUGGING: Matched ANALYZER (Default)")
                        response_content = """
                        {
                            "refactoring_targets": [
                                {
                                    "filepath": "user_stats.py",
                                    "node_type": "function",
                                    "node_name": "process_user_data",
                                    "start_line": 1,
                                    "end_line": 15,
                                    "description": "Add type hints and improve variable names"
                                }
                            ]
                        }
                        """
                
                # 2. Generator Response
                elif "generate" in msg_lower or "original code" in msg_lower or "transform" in msg_lower:
                    if "calculate_metrics" in msg_lower or "process_data" in msg_lower:
                        response_content = '''[SUMMARY]
Added type hints to all functions. Fixed potential ZeroDivisionError in calculate_metrics by returning 0.0 when count is zero.

[CODE]
```python
from typing import List, Dict, Any

def calculate_metrics(data_list: List[Dict[str, Any]]) -> float:
    """Calculate average score from a list of dictionaries."""
    total_score = 0
    count = 0
    
    for item in data_list:
        if 'score' in item:
            total_score += item['score']
            count += 1
            
    if count == 0:
        return 0.0
    
    return total_score / count

def process_data(raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process raw data and return list of processed entries."""
    processed = []
    for entry in raw_data:
        if entry.get('active') is True:
            result = calculate_metrics(entry.get('history', []))
            processed.append({"id": entry['id'], "avg": result})
            
    return processed
```'''
                    else:
                        response_content = '''[SUMMARY]
Added type hints to the process_user_data function. Improved variable naming and added docstring.

[CODE]
```python
from typing import List, Dict, Any, Union

def process_user_data(users: List[Dict[str, Any]]) -> Dict[str, Union[int, float]]:
    """
    Process user data and return statistics.
    
    Args:
        users: List of user dictionaries.
        
    Returns:
        Dictionary with count and average age.
    """
    total_age = 0
    valid_users = []
    
    for user in users:
        if user.get('age') and user.get('name'):
            total_age += user['age']
            valid_users.append(user)
            
    average_age = 0.0
    if valid_users:
        average_age = total_age / len(valid_users)

    return {"count": len(valid_users), "average_age": average_age}
```'''
                
                # 3. Reflector Response
                else:
                    print(f"DEBUGGING: Matched REFLECTOR (Fallback) - {msg_lower[:50]}")
                    response_content = "The code looks good but could use more docstrings."
                
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=response_content))])

            @property
            def _llm_type(self) -> str:
                return "mock-ara-llm"
                
        return MockAraLLM()

    model = model or settings.llm_model

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        # Import exception for rate limit handling
        from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

        # Configure LLM with built-in retry logic
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.gemini_api_key,
            temperature=temperature,
            convert_system_message_to_human=True,
            # Robust settings for production
            max_retries=10, 
            request_timeout=60,
        )

        logger.info("llm_initialized_production", provider="gemini", model=model)
        return llm

    except ImportError:
        raise ImportError(
            "langchain-google-genai is required. "
            "Install with: pip install langchain-google-genai"
        )
    except Exception as e:
        logger.error("llm_initialization_failed", error=str(e))
        raise


def get_llm_with_structured_output(
    output_schema,
    model: Optional[str] = None,
    temperature: float = 0.0,
):
    """
    Get an LLM configured for structured output.

    Args:
        output_schema: Pydantic model or dict schema for output
        model: Model name override
        temperature: Temperature for generation

    Returns:
        LLM configured to output structured data
    """
    llm = get_llm(model=model, temperature=temperature)
    return llm.with_structured_output(output_schema)
