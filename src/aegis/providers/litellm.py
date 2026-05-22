"""LiteLLM catch-all provider — routes to 100+ backends with a unified call."""

from __future__ import annotations

import json
from typing import Any

from aegis.providers.base import Completion, Message, Tool, ToolCall, _messages_to_dicts


class LiteLLM:
    """Adapter that delegates to the LiteLLM router.

    >>> LiteLLM(model="bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0")
    """

    name = "litellm"

    def __init__(self, model: str = "gpt-4o", **kwargs: Any) -> None:
        self.model = model
        self._kwargs = kwargs

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_only: bool = False,
    ) -> Completion:
        try:
            import litellm
        except ImportError as e:
            raise ImportError(
                "LiteLLM provider requires `pip install aegis-harness[litellm]`"
            ) from e

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": _messages_to_dicts(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            **self._kwargs,
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

        response = await litellm.acompletion(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        tool_calls: list[ToolCall] = []
        for tc in getattr(msg, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        usage = getattr(response, "usage", None)
        return Completion(
            text=getattr(msg, "content", "") or "",
            tool_calls=tool_calls,
            tokens_in=getattr(usage, "prompt_tokens", 0) if usage else 0,
            tokens_out=getattr(usage, "completion_tokens", 0) if usage else 0,
            finish_reason=getattr(choice, "finish_reason", "stop") or "stop",
        )
