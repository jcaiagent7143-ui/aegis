"""FastAPI server implementing the OpenAI ``/v1/chat/completions`` shape.

Two modes selected per request via the ``X-Aegis-Mode`` header (defaults to
``aegis``):

  * ``aegis``      — Treat the last user message as a goal. Run the full
                     5-stage Aegis pipeline. Return the verified value as the
                     assistant's message content.
  * ``passthrough`` — Forward the request directly to the upstream provider
                     (configured at startup) and just log it. Use for tools
                     that need raw chat for non-agentic prompts.

Endpoints implemented (the subset clients actually call):

  * ``GET  /v1/models``
  * ``POST /v1/chat/completions``  (streaming and non-streaming)
  * ``GET  /health``

This is a minimal OpenAI shim — it isn't a full reimplementation. Tools that
need /v1/embeddings, /v1/audio etc. should hit the upstream provider directly.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from aegis import Aegis
from aegis.providers.base import Message


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    response_format: dict[str, Any] | None = None
    # We tolerate any other fields without failing
    model_config = {"extra": "allow"}


def build_app(
    *,
    cache_dir: Path | str | None = None,
    default_mode: Literal["aegis", "passthrough"] = "aegis",
) -> FastAPI:
    app = FastAPI(
        title="Aegis OpenAI-compatible proxy",
        docs_url="/api/docs",
        version="0.4.0",
    )
    aegis = Aegis(cache_dir=cache_dir or ".aegis")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "provider": aegis.provider.name,
            "model": getattr(aegis.provider, "model", ""),
        }

    @app.get("/v1/models")
    def list_models() -> dict[str, Any]:
        """Minimal models endpoint — advertises one model: the configured one."""
        m = getattr(aegis.provider, "model", "aegis")
        return {
            "object": "list",
            "data": [
                {
                    "id": "aegis",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "aegis",
                    "permission": [],
                },
                {
                    "id": m,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": aegis.provider.name,
                    "permission": [],
                },
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(
        req: Request,
        x_aegis_mode: str | None = Header(default=None),
    ) -> Any:
        body = await req.json()
        try:
            request = ChatCompletionRequest.model_validate(body)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid request: {e}") from e

        mode = (x_aegis_mode or default_mode).lower()
        if mode not in ("aegis", "passthrough"):
            raise HTTPException(status_code=400, detail="X-Aegis-Mode must be aegis|passthrough")

        if mode == "aegis":
            return await _handle_aegis(aegis, request)
        return await _handle_passthrough(aegis, request)

    return app


# ── mode: aegis ─────────────────────────────────────────────────────────────


async def _handle_aegis(aegis: Aegis, request: ChatCompletionRequest) -> Any:
    """Extract the goal from the conversation and run the Aegis pipeline."""
    goal = _extract_goal(request.messages)
    if not goal:
        raise HTTPException(status_code=400, detail="no user message found in request")

    result = await aegis.run(goal)

    # Render the value as the assistant message
    if isinstance(result.value, str):
        content = result.value
    else:
        content = json.dumps(result.value, indent=2, default=str)

    response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model = getattr(aegis.provider, "model", "aegis")

    if request.stream:
        return StreamingResponse(
            _stream_text(response_id, created, model, content, result),
            media_type="text/event-stream",
        )

    return {
        "id": response_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "system_fingerprint": "aegis",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop" if result.audit.succeeded else "content_filter",
            }
        ],
        "usage": {
            "prompt_tokens": _prompt_tokens(result),
            "completion_tokens": _completion_tokens(result),
            "total_tokens": result.audit.total_tokens,
        },
        "aegis": {
            "run_id": result.audit.run_id,
            "succeeded": result.audit.succeeded,
            "risks": [r.id for r in result.audit.risks.risks],
            "repairs": result.audit.repairs,
            "harness_code": result.harness_code,
            "tool_calls": [{"name": t["name"], "ok": t["ok"]} for t in result.audit.tool_calls],
        },
    }


def _extract_goal(messages: list[ChatMessage]) -> str:
    """Use the last user message as the goal; concatenate any preceding system prompts as context."""
    for m in reversed(messages):
        if m.role == "user":
            return _stringify_content(m.content)
    return ""


def _stringify_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    # OpenAI multimodal: list of {type, text|image_url|...}
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text", "")))
        return "\n".join(parts)
    return str(content)


async def _stream_text(
    response_id: str,
    created: int,
    model: str,
    text: str,
    result: Any,
):
    """Emit OpenAI-style SSE chunks for streaming clients."""
    # Initial role chunk
    yield _sse(
        {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
    )
    # Send the text in modest chunks for a streaming feel
    chunk_size = 80
    for i in range(0, len(text), chunk_size):
        yield _sse(
            {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": text[i : i + chunk_size]},
                        "finish_reason": None,
                    }
                ],
            }
        )
    # Final chunk + DONE marker
    yield _sse(
        {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop" if result.audit.succeeded else "content_filter",
                }
            ],
            "aegis": {
                "run_id": result.audit.run_id,
                "succeeded": result.audit.succeeded,
                "risks": [r.id for r in result.audit.risks.risks],
            },
        }
    )
    yield "data: [DONE]\n\n"


def _sse(payload: dict[str, Any]) -> str:
    return "data: " + json.dumps(payload, default=str) + "\n\n"


def _prompt_tokens(result: Any) -> int:
    return sum(s.tokens_in for s in result.audit.stages)


def _completion_tokens(result: Any) -> int:
    return sum(s.tokens_out for s in result.audit.stages)


# ── mode: passthrough ──────────────────────────────────────────────────────


async def _handle_passthrough(aegis: Aegis, request: ChatCompletionRequest) -> Any:
    """Forward to the configured Aegis provider as a one-shot completion."""
    msgs = [
        Message(
            role=m.role,
            content=_stringify_content(m.content),
            name=m.name,
            tool_call_id=m.tool_call_id,
        )
        for m in request.messages
    ]
    completion = await aegis.provider.complete(
        msgs,
        temperature=request.temperature if request.temperature is not None else 0.2,
        max_tokens=(request.max_completion_tokens or request.max_tokens or 4096),
        json_only=bool(
            request.response_format and request.response_format.get("type") == "json_object"
        ),
    )
    response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    return {
        "id": response_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": getattr(aegis.provider, "model", "aegis"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": completion.text},
                "finish_reason": completion.finish_reason or "stop",
            }
        ],
        "usage": {
            "prompt_tokens": completion.tokens_in,
            "completion_tokens": completion.tokens_out,
            "total_tokens": completion.tokens_in + completion.tokens_out,
        },
    }
