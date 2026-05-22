"""OpenAI provider — chat-completions backend with multi-turn tool use.

Notes for newer models (gpt-5.x family, o-series): they only accept
``max_completion_tokens``; older models accept ``max_tokens``. We always send
``max_completion_tokens`` because that name is forward-compatible.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Any

from aegis.providers.base import Completion, Message, Tool, ToolCall, to_openai_dicts


class OpenAI:
    """Adapter for OpenAI chat models.

    Parameters
    ----------
    model:
        OpenAI model id. Defaults to ``gpt-4o-mini`` (cheap + fast); pass
        ``gpt-5.4-nano-2026-03-17``, ``gpt-5``, ``gpt-4o``, etc. as needed.
    api_key:
        Optional override; otherwise reads ``OPENAI_API_KEY`` from env.
    base_url:
        Optional override for self-hosted OpenAI-compatible servers.
    max_retries:
        How many times to retry on transient errors (rate-limits, 5xx).
    """

    name = "openai"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        # Eagerly verify the openai package is importable so a missing-extra
        # install produces a clear ImportError at construction time rather
        # than 4 stages deep inside the pipeline. (Bug found in v0.5.3 e2e
        # test: auto_provider() returned OpenAI() successfully because the
        # openai import is lazy, then the analyze stage crashed with a deep
        # traceback users couldn't easily map back to a missing extra.)
        if client is None:
            try:
                import openai  # noqa: F401
            except ImportError as e:
                raise ImportError(
                    "OpenAI provider requires the `openai` package. "
                    'Install with: pip install "self-harness[openai]"'
                ) from e
        # Honor AEGIS_MODEL override for everyone (cli, mcp, proxy, lib).
        self.model = model or os.environ.get("AEGIS_MODEL") or "gpt-4o-mini"
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url
        self._max_retries = max_retries
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError("OpenAI provider requires `pip install self-harness[openai]`") from e
        self._client = AsyncOpenAI(api_key=self._api_key or None, base_url=self._base_url)
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

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": to_openai_dicts(messages),
            # Use the forward-compatible name — works on gpt-4o family and
            # required on gpt-5.x / o-series.
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = [
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
        if json_only:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._retry(client, kwargs)
        choice = response.choices[0]
        msg = choice.message

        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": tc.function.arguments}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        usage = getattr(response, "usage", None)
        return Completion(
            text=msg.content or "",
            tool_calls=tool_calls,
            tokens_in=getattr(usage, "prompt_tokens", 0) if usage else 0,
            tokens_out=getattr(usage, "completion_tokens", 0) if usage else 0,
            finish_reason=choice.finish_reason or "stop",
            raw={"id": getattr(response, "id", "")},
        )

    async def _retry(self, client: Any, kwargs: dict[str, Any]) -> Any:
        """Call chat.completions.create with bounded retries on transient errors."""
        from openai import APIConnectionError, APIError, RateLimitError

        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await client.chat.completions.create(**kwargs)
            except RateLimitError as e:
                last_exc = e
            except APIConnectionError as e:
                last_exc = e
            except APIError as e:
                # Retry on 5xx only
                status = getattr(e, "status_code", None) or getattr(e, "code", None)
                if isinstance(status, int) and 500 <= status < 600:
                    last_exc = e
                else:
                    raise
            if attempt < self._max_retries:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 16.0)
        assert last_exc is not None
        raise last_exc

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_only: bool = False,
    ) -> AsyncIterator[tuple[str, str | Completion]]:
        """Streaming variant — yields text deltas as the model produces them.

        For tool-call streaming we accumulate the deltas and emit the assembled
        Completion at the end. Pure-text streams emit ``("delta", str)`` events
        and finish with ``("done", Completion)``.
        """
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": to_openai_dicts(messages),
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = [
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
        if json_only:
            kwargs["response_format"] = {"type": "json_object"}

        text_parts: list[str] = []
        tool_acc: dict[int, dict[str, Any]] = {}
        tokens_in = tokens_out = 0
        finish_reason = "stop"

        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage:
                tokens_in = usage.prompt_tokens or 0
                tokens_out = usage.completion_tokens or 0
            if not chunk.choices:
                continue
            ch = chunk.choices[0]
            delta = ch.delta
            if delta.content:
                text_parts.append(delta.content)
                yield ("delta", delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = tool_acc.setdefault(tc.index, {"id": None, "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    fn = tc.function
                    if fn and fn.name:
                        slot["name"] += fn.name
                    if fn and fn.arguments:
                        slot["args"] += fn.arguments
            if ch.finish_reason:
                finish_reason = ch.finish_reason

        tool_calls: list[ToolCall] = []
        for slot in tool_acc.values():
            try:
                args = json.loads(slot["args"] or "{}")
            except json.JSONDecodeError:
                args = {"_raw": slot["args"]}
            tool_calls.append(ToolCall(id=slot["id"] or "", name=slot["name"], arguments=args))

        yield (
            "done",
            Completion(
                text="".join(text_parts),
                tool_calls=tool_calls,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                finish_reason=finish_reason,
            ),
        )
