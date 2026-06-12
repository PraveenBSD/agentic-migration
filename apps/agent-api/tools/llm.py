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

try:
    from langchain_ollama import ChatOllama
except Exception:  # pragma: no cover
    ChatOllama = None

from .registry import TOOLS


def get_llm(tools: List[Any] | None = None) -> Any:
    provider = os.getenv("MIGRATION_LLM_PROVIDER", "openai").strip().lower()
    tool_list = tools or TOOLS

    if provider == "ollama":
        if ChatOllama is None:
            return None
        model = os.getenv("MIGRATION_LLM_MODEL", "llama3.1")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        llm = ChatOllama(model=model, base_url=base_url, temperature=0)
        return llm.bind_tools(tool_list)

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
        raise ValueError("MIGRATION_LLM_PROVIDER must be one of 'openai', 'gemini', or 'ollama'")

    if not os.getenv("OPENAI_API_KEY") or ChatOpenAI is None:
        return None

    model = os.getenv("MIGRATION_LLM_MODEL", "gpt-4o")
    llm = ChatOpenAI(model=model, temperature=0)
    return llm.bind_tools(tool_list)


def llm_provider_config() -> dict[str, str]:
    provider = os.getenv("MIGRATION_LLM_PROVIDER", "openai").strip().lower()
    defaults = {
        "gemini": ("gemini-2.5-flash", "GOOGLE_API_KEY"),
        "ollama": ("llama3.1", ""),
        "openai": ("gpt-4o", "OPENAI_API_KEY"),
    }
    default_model, api_key_name = defaults.get(provider, defaults["openai"])
    configured = bool(ChatOllama) if provider == "ollama" else bool(os.getenv(api_key_name))
    return {
        "provider": provider,
        "model": os.getenv("MIGRATION_LLM_MODEL", default_model),
        "api_key_name": api_key_name,
        "configured": str(configured).lower(),
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") if provider == "ollama" else "",
    }
