from __future__ import annotations

from typing import Any


def invoke_tool(tool_func: Any, tool_input: dict) -> str:
    """Safely invoke a tool and return the result as a string."""
    try:
        # Try .invoke() method first (LangChain tools)
        if hasattr(tool_func, "invoke"):
            result = tool_func.invoke(tool_input)
        # Try calling directly (should work for decorated functions)
        else:
            result = tool_func(**tool_input)
        return str(result)
    except Exception as exc:
        return f"Error invoking {getattr(tool_func, 'name', 'unknown')}: {exc}"
