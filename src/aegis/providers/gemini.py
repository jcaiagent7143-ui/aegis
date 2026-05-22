"""Google Gemini provider — `google-genai` SDK adapter.

Maps Aegis's internal Message/Tool/Completion shape onto Gemini's
``Content``/``Part``/``FunctionDeclaration`` shape. Like Anthropic, Gemini
does not have a separate ``tool`` role; tool results are user-role messages
containing a ``functionResponse`` part.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from aegis.providers.base import Completion, Message, Tool, ToolCall


class Gemini:
    """Adapter for Google Gemini models via the ``google-genai`` SDK.

    Default model is ``gemini-2.0-flash`` (fast + cheap); pass
    ``gemini-2.5-pro`` etc. as needed.
    """

    name = "gemini"

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        api_key: str | None = None,
        *,
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self._api_key = (
            api_key or os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        )
        self._max_retries = max_retries
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google import genai
        except ImportError as e:
            raise ImportError("Gemini provider requires `pip install aegis-harness[gemini]`") from e
        self._client = genai.Client(api_key=self._api_key or None)
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

        system_text, contents = _to_gemini(messages)

        from google.genai import types as gt

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system_text:
            if json_only:
                system_text = f"{system_text}\n\nRespond with raw JSON only — no prose."
            config_kwargs["system_instruction"] = system_text
        elif json_only:
            config_kwargs["system_instruction"] = "Respond with raw JSON only — no prose."

        if json_only:
            config_kwargs["response_mime_type"] = "application/json"

        if tools:
            decls = [
                gt.FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters=t.parameters_schema or {"type": "object", "properties": {}},
                )
                for t in tools
            ]
            config_kwargs["tools"] = [gt.Tool(function_declarations=decls)]

        response = await self._retry(client, contents, gt.GenerateContentConfig(**config_kwargs))

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        cand = response.candidates[0] if response.candidates else None
        if cand and cand.content and cand.content.parts:
            for part in cand.content.parts:
                if getattr(part, "text", None):
                    text_parts.append(part.text)
                fc = getattr(part, "function_call", None)
                if fc:
                    tool_calls.append(
                        ToolCall(
                            id=getattr(fc, "id", "") or f"call_{len(tool_calls)}",
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                        )
                    )

        usage = getattr(response, "usage_metadata", None)
        return Completion(
            text="".join(text_parts),
            tool_calls=tool_calls,
            tokens_in=getattr(usage, "prompt_token_count", 0) if usage else 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) if usage else 0,
            finish_reason=str(getattr(cand, "finish_reason", "stop")) if cand else "stop",
        )

    async def _retry(self, client: Any, contents: list[Any], config: Any) -> Any:
        from google.genai import errors as gerr

        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await client.aio.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
            except gerr.APIError as e:
                status = getattr(e, "code", 0)
                if 500 <= int(status or 0) < 600 or status == 429:
                    last_exc = e
                else:
                    raise
            except Exception as e:  # network etc.
                last_exc = e
            if attempt < self._max_retries:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 16.0)
        assert last_exc is not None
        raise last_exc


def _to_gemini(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """Translate Aegis messages → (system_instruction, list[Content])."""
    system_parts: list[str] = [m.content for m in messages if m.role == "system"]
    contents: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "assistant":
            parts: list[dict[str, Any]] = []
            if m.content:
                parts.append({"text": m.content})
            for tc in m.tool_calls:
                parts.append({"function_call": {"name": tc.name, "args": tc.arguments}})
            contents.append({"role": "model", "parts": parts})
        elif m.role == "tool":
            # Gemini represents tool results as a user message with a
            # functionResponse part. ``name`` must match the function name.
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": m.name or "",
                                "response": {"content": m.content},
                            }
                        }
                    ],
                }
            )
        else:  # user
            contents.append({"role": "user", "parts": [{"text": m.content}]})
    return "\n\n".join(system_parts), contents
