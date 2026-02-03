"""
Direct LLM Test Script - Tests if Gemini is responding correctly.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

def test_llm():
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("LLM_MODEL", "gemini-3-pro-preview")
    
    print(f"Testing model: {model}")
    print(f"API Key (first 10 chars): {api_key[:10]}...")
    
    try:
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0.0,
            convert_system_message_to_human=True,
            max_retries=0,  # Fail fast
            request_timeout=30,
        )
        
        messages = [
            SystemMessage(content="You are a Python expert. Respond with [SUMMARY] and [CODE] blocks."),
            HumanMessage(content="""Refactoring Goal: Add type hints

Original Code:
```python
def add(a, b):
    return a + b
```

Generate the [SUMMARY] and [CODE].""")
        ]
        
        print("\n--- Calling LLM ---")
        response = llm.invoke(messages)
        print("\n--- RAW RESPONSE ---")
        print(response.content)
        print("\n--- END RESPONSE ---")
        
        # Test parsing
        import re
        code_match = re.search(r'```python(.*?)```', response.content, re.DOTALL)
        if code_match:
            print("\n✅ Code block found:")
            print(code_match.group(1).strip())
        else:
            print("\n❌ No code block found!")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_llm()
