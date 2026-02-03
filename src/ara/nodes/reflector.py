"""
Reflector Node - The Teacher.

This node analyzes validation failures and generates reflection notes
to guide the Generator in its next attempt. Implements the Reflexion pattern.
"""

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from ara.state.schema import AgentState
from ara.state.models import ReflectionNote, ValidationResult
from ara.llm.provider import get_llm

logger = structlog.get_logger()


REFLECTOR_SYSTEM_PROMPT = """You are a code review expert helping to fix a failed code transformation. Your task is to analyze the error messages and provide clear, actionable guidance.

ANALYSIS APPROACH:
1. Identify the ROOT CAUSE of each error
2. Explain WHY the error occurred in simple terms
3. Provide SPECIFIC fixes with exact code changes needed
4. If there are multiple errors, prioritize them by severity

OUTPUT FORMAT:
Provide a concise analysis with:
1. Error Summary: What went wrong (1-2 sentences)
2. Root Cause: Why it happened
3. Suggested Fix: Exact changes needed to fix the issue

Be specific and actionable. Reference line numbers when available."""


def reflector_node(state: AgentState) -> dict:
    """
    Analyze validation failures and generate reflection notes.

    This node:
    1. Gets the latest validation results
    2. Analyzes the errors using LLM
    3. Generates a structured reflection note
    4. Increments the iteration counter

    Args:
        state: Current agent state

    Returns:
        Updated state with reflection_history and incremented iteration_count
    """
    validation_history = state.get("validation_history", [])
    generated_code = state.get("generated_code_snippet", "")
    iteration_count = state.get("iteration_count", 0)

    logger.info("reflector_start", iteration=iteration_count)

    if not validation_history:
        logger.warning("reflector_no_validation_history")
        return {
            "iteration_count": iteration_count + 1,
            "reflection_history": [
                ReflectionNote(
                    iteration=iteration_count,
                    error_summary="No validation results available",
                    suggested_fix="Please run validation first",
                )
            ],
        }

    # Get the most recent failed validation results
    recent_failures = [
        v for v in validation_history[-5:]  # Last 5 results
        if isinstance(v, ValidationResult) and not v.passed
    ]

    if not recent_failures:
        # No failures to reflect on
        logger.info("reflector_no_failures")
        return {"iteration_count": iteration_count + 1}

    # Build error context for LLM
    error_context = _build_error_context(recent_failures)

    try:
        llm = get_llm(temperature=0.0)

        messages = [
            SystemMessage(content=REFLECTOR_SYSTEM_PROMPT),
            HumanMessage(content=f"""The following code transformation failed validation:

Generated Code:
```python
{generated_code[:2000]}  # Truncate if too long
```

Validation Errors:
{error_context}

Analyze these errors and provide specific guidance to fix them.""")
        ]

        response = llm.invoke(messages)
        reflection_text = response.content

        logger.info("reflector_complete", reflection_length=len(reflection_text))

        # Extract key information for the reflection note
        error_summary, suggested_fix = _parse_reflection(reflection_text)

        # Get relevant error lines
        relevant_errors = []
        for failure in recent_failures:
            if failure.error_message:
                relevant_errors.append(failure.error_message[:200])

        reflection_note = ReflectionNote(
            iteration=iteration_count,
            error_summary=error_summary,
            suggested_fix=suggested_fix,
            relevant_error_lines=relevant_errors[:5],
        )

        return {
            "iteration_count": iteration_count + 1,
            "reflection_history": [reflection_note],
            "human_feedback": reflection_text,  # Full analysis for context
        }

    except Exception as e:
        logger.error("reflector_error", error=str(e))
        return {
            "iteration_count": iteration_count + 1,
            "reflection_history": [
                ReflectionNote(
                    iteration=iteration_count,
                    error_summary=f"Reflection failed: {str(e)}",
                    suggested_fix="Please review the errors manually",
                )
            ],
        }


def _build_error_context(failures: list) -> str:
    """
    Build a formatted error context from validation failures.

    Args:
        failures: List of failed ValidationResult objects

    Returns:
        Formatted error string
    """
    context_parts = []

    for i, failure in enumerate(failures, 1):
        parts = [f"Error {i} ({failure.tool_name}):"]

        if failure.error_message:
            parts.append(f"  Message: {failure.error_message}")

        if failure.stderr and failure.stderr != failure.error_message:
            # Truncate stderr if too long
            stderr = failure.stderr[:500]
            parts.append(f"  Stderr: {stderr}")

        if failure.stdout:
            stdout = failure.stdout[:300]
            parts.append(f"  Stdout: {stdout}")

        context_parts.append("\n".join(parts))

    return "\n\n".join(context_parts)


def _parse_reflection(reflection_text: str) -> tuple:
    """
    Parse the LLM reflection into error summary and suggested fix.

    Args:
        reflection_text: Raw LLM response

    Returns:
        Tuple of (error_summary, suggested_fix)
    """
    lines = reflection_text.strip().split("\n")

    error_summary = ""
    suggested_fix = ""

    current_section = None
    for line in lines:
        line_lower = line.lower()

        if "error summary" in line_lower or "what went wrong" in line_lower:
            current_section = "summary"
            continue
        elif "root cause" in line_lower:
            current_section = "cause"
            continue
        elif "suggested fix" in line_lower or "fix" in line_lower:
            current_section = "fix"
            continue

        if current_section == "summary" and line.strip():
            error_summary += line.strip() + " "
        elif current_section == "fix" and line.strip():
            suggested_fix += line.strip() + " "

    # Fallback if parsing failed
    if not error_summary:
        error_summary = reflection_text[:200]
    if not suggested_fix:
        suggested_fix = reflection_text[200:400] if len(reflection_text) > 200 else ""

    return error_summary.strip(), suggested_fix.strip()
