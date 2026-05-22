"""Anthropic Claude provider — primary recommended adapter.

Anthropic's messages API uses content blocks (``text``, ``tool_use``,
``tool_result``) inside messages, not separate roles for tool messages. The
``to_anthropic`` helper in ``providers.base`` does the translation.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from aegis.providers.base import Completion, Message, Tool, ToolCall, to_anthropic


class Anthropic:
    """Adapter for Anthropic's Claude models.

    Default model: ``claude-opus-4-7`` (best reasoning quality for synthesis).
    """

    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-opus-4-7",
        api_key: str | None = None,
        *,
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._max_retries = max_retries
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "Anthropic provider requires `pip install self-harness[anthropic]`"
            ) from e
        self._client = anthropic.AsyncAnthropic(api_key=self._api_key or None)
        return self._client

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_only: bool = False,
    ) -> Completion:
        client = self._get_client()
        system, convo = to_anthropic(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": convo,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            if json_only:
                system = f"{system}\n\nRespond with raw JSON only — no prose."
            kwargs["system"] = system
        elif json_only:
            kwargs["system"] = "Respond with raw JSON only — no prose."
        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters_schema or {"type": "object", "properties": {}},
                }
                for t in tools
            ]

        response = await self._retry(client, kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input) if block.input else {},
                    )
                )

        usage = getattr(response, "usage", None)
        return Completion(
            text="".join(text_parts),
            tool_calls=tool_calls,
            tokens_in=getattr(usage, "input_tokens", 0) if usage else 0,
            tokens_out=getattr(usage, "output_tokens", 0) if usage else 0,
            finish_reason=getattr(response, "stop_reason", "stop") or "stop",
            raw={"id": getattr(response, "id", "")},
        )

    async def _retry(self, client: Any, kwargs: dict[str, Any]) -> Any:
        import anthropic

        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await client.messages.create(**kwargs)
            except (anthropic.RateLimitError, anthropic.APIConnectionError) as e:
                last_exc = e
            except anthropic.APIStatusError as e:
                status = getattr(e, "status_code", 0)
                if 500 <= status < 600:
                    last_exc = e
                else:
                    raise
            if attempt < self._max_retries:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 16.0)
        assert last_exc is not None
        raise last_exc
