from __future__ import annotations

import os
from typing import Any, List

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover
    ChatGoogleGenerativeAI = None

from .registry import TOOLS


def get_llm(tools: List[Any] | None = None) -> Any:
    provider = os.getenv("MIGRATION_LLM_PROVIDER", "openai").strip().lower()
    tool_list = tools or TOOLS

    if provider == "gemini":
        if not os.getenv("GOOGLE_API_KEY") or ChatGoogleGenerativeAI is None:
            return None
        model = os.getenv("MIGRATION_LLM_MODEL", "gemini-2.5-flash")
        llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
        return llm.bind_tools(tool_list)

    if provider != "openai":
        raise ValueError("MIGRATION_LLM_PROVIDER must be either 'openai' or 'gemini'")

    if not os.getenv("OPENAI_API_KEY") or ChatOpenAI is None:
        return None

    model = os.getenv("MIGRATION_LLM_MODEL", "gpt-4o")
    llm = ChatOpenAI(model=model, temperature=0)
    return llm.bind_tools(tool_list)


def llm_provider_config() -> dict[str, str]:
    provider = os.getenv("MIGRATION_LLM_PROVIDER", "openai").strip().lower()
    default_model = "gemini-2.5-flash" if provider == "gemini" else "gpt-4o"
    api_key_name = "GOOGLE_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
    return {
        "provider": provider,
        "model": os.getenv("MIGRATION_LLM_MODEL", default_model),
        "api_key_name": api_key_name,
        "configured": str(bool(os.getenv(api_key_name))).lower(),
    }
