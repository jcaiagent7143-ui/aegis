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

    If a provider's API key is set but its extra is not installed, we log a
    loud warning before falling through. This catches the most common
    footgun ("I set OPENAI_API_KEY but `aegis run` still returned `[mock]`")
    that we hit in our own v0.5.3 end-to-end test.
    """
    import sys

    requested: list[str] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        requested.append("anthropic")
        try:
            from aegis.providers.anthropic import Anthropic

            return Anthropic()
        except ImportError:
            sys.stderr.write(
                "[aegis] WARNING: ANTHROPIC_API_KEY is set but the `anthropic` "
                'package is not installed. Install with: pip install "self-harness[anthropic]"\n'
            )
    if os.environ.get("OPENAI_API_KEY"):
        requested.append("openai")
        try:
            from aegis.providers.openai import OpenAI

            return OpenAI()
        except ImportError:
            sys.stderr.write(
                "[aegis] WARNING: OPENAI_API_KEY is set but the `openai` "
                'package is not installed. Install with: pip install "self-harness[openai]"\n'
            )
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        requested.append("gemini")
        try:
            from aegis.providers.gemini import Gemini

            return Gemini()
        except ImportError:
            sys.stderr.write(
                "[aegis] WARNING: GOOGLE_API_KEY/GEMINI_API_KEY is set but the "
                "`google-genai` package is not installed. Install with: "
                'pip install "self-harness[gemini]"\n'
            )
    # Ollama is local; try a quick connection check
    if os.environ.get("OLLAMA_HOST") or _ollama_alive():
        requested.append("ollama")
        try:
            from aegis.providers.ollama import Ollama

            return Ollama()
        except ImportError:
            sys.stderr.write(
                "[aegis] WARNING: Ollama looks available but the `ollama` "
                'package is not installed. Install with: pip install "self-harness[ollama]"\n'
            )
    # Fallback: Mock provider so the package is always importable & runnable.
    # We tag the instance as an auto-fallback so the pipeline can refuse to
    # poison the harness cache with results from a Mock that the user
    # almost certainly did NOT want to be running.
    if requested:
        sys.stderr.write(
            f"[aegis] WARNING: falling back to Mock provider — you set "
            f"{'/'.join(requested).upper()}_API_KEY but the matching extra is "
            "missing. All results will be placeholder text starting with `[mock]`.\n"
        )
    from aegis.providers.mock import Mock

    mock = Mock()
    mock._is_auto_fallback = True  # type: ignore[attr-defined]
    return mock


def _ollama_alive() -> bool:
    try:
        import httpx

        r = httpx.get("http://localhost:11434/api/tags", timeout=0.3)
        return r.status_code == 200
    except Exception:
        return False
