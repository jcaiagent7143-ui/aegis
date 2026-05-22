"""LLM provider adapters."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from aegis.providers.base import Completion, Message, Provider, Tool

if TYPE_CHECKING:
    pass

__all__ = [
    "Anthropic",
    "Completion",
    "Gemini",
    "LiteLLM",
    "Message",
    "Mock",
    "Ollama",
    "OpenAI",
    "Provider",
    "Tool",
    "auto_provider",
]


def __getattr__(name: str) -> object:
    # Lazy imports so missing optional deps don't break `from aegis.providers import X`
    if name == "Anthropic":
        from aegis.providers.anthropic import Anthropic

        return Anthropic
    if name == "OpenAI":
        from aegis.providers.openai import OpenAI

        return OpenAI
    if name == "Gemini":
        from aegis.providers.gemini import Gemini

        return Gemini
    if name == "Ollama":
        from aegis.providers.ollama import Ollama

        return Ollama
    if name == "LiteLLM":
        from aegis.providers.litellm import LiteLLM

        return LiteLLM
    if name == "Mock":
        from aegis.providers.mock import Mock

        return Mock
    raise AttributeError(f"module 'aegis.providers' has no attribute {name!r}")


def auto_provider() -> Provider:
    """Pick the best available provider based on environment variables.

    Order: Anthropic → OpenAI → Gemini → Ollama → Mock.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from aegis.providers.anthropic import Anthropic

            return Anthropic()
        except ImportError:
            pass
    if os.environ.get("OPENAI_API_KEY"):
        try:
            from aegis.providers.openai import OpenAI

            return OpenAI()
        except ImportError:
            pass
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        try:
            from aegis.providers.gemini import Gemini

            return Gemini()
        except ImportError:
            pass
    # Ollama is local; try a quick connection check
    if os.environ.get("OLLAMA_HOST") or _ollama_alive():
        try:
            from aegis.providers.ollama import Ollama

            return Ollama()
        except ImportError:
            pass
    # Fallback: Mock provider so the package is always importable & runnable
    from aegis.providers.mock import Mock

    return Mock()


def _ollama_alive() -> bool:
    try:
        import httpx

        r = httpx.get("http://localhost:11434/api/tags", timeout=0.3)
        return r.status_code == 200
    except Exception:
        return False
