"""Ollama provider — local, free, runs against `localhost:11434` by default."""

from __future__ import annotations

import os
from typing import Any

import httpx

from aegis.providers.base import Completion, Message, Tool, _messages_to_dicts


class Ollama:
    """Adapter for a local Ollama server.

    >>> Ollama(model="llama3.1:70b")
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.1",
        host: str | None = None,
        *,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self._timeout = timeout

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_only: bool = False,
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _messages_to_dicts(messages),
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_only:
            payload["format"] = "json"
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters_schema or {"type": "object", "properties": {}},
                    },
                }
                for t in tools
            ]

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(f"{self.host}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()

        text = (data.get("message") or {}).get("content", "") or ""
        return Completion(
            text=text,
            tokens_in=data.get("prompt_eval_count", 0) or 0,
            tokens_out=data.get("eval_count", 0) or 0,
            finish_reason="stop",
            raw={"model": data.get("model")},
        )
