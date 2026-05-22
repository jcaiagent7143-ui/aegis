"""Provider Protocol — every LLM adapter implements this.

The Message + Completion model is deliberately a small superset of the OpenAI
chat schema, mapped onto Anthropic's content-block format inside that adapter.
This is the single shape every stage in the pipeline produces and consumes.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    """A tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    """A single chat message — superset of OpenAI's chat format."""

    role: Role
    content: str = ""
    name: str | None = None
    # Only set on assistant messages that triggered tool calls. The next
    # message(s) MUST be role="tool" replies with matching tool_call_id.
    tool_calls: list[ToolCall] = Field(default_factory=list)
    # Only set on role="tool" messages.
    tool_call_id: str | None = None

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str = "", tool_calls: list[ToolCall] | None = None) -> Message:
        return cls(role="assistant", content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool_result(cls, tool_call_id: str, name: str, content: str) -> Message:
        return cls(role="tool", content=content, name=name, tool_call_id=tool_call_id)


class Tool(BaseModel):
    """Tool description passed to the provider."""

    name: str
    description: str
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


class Completion(BaseModel):
    """The model's response."""

    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    finish_reason: str = "stop"
    raw: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Provider(Protocol):
    """Anything that can turn messages into a Completion."""

    name: str
    model: str

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_only: bool = False,
    ) -> Completion:
        """Return a single completion."""
        ...


# ── shared serialization helpers ───────────────────────────────────────────


def to_openai_dicts(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert internal messages to OpenAI chat-completions schema.

    Critical: assistant messages with tool_calls must include the `tool_calls`
    array, and the following tool messages must reference matching tool_call_id.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        d: dict[str, Any] = {"role": m.role}
        # OpenAI accepts null content on assistant messages with tool_calls,
        # but pydantic strings can't be None — coerce empty strings to None.
        if m.role == "assistant" and m.tool_calls:
            d["content"] = m.content or None
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": _json_dumps(tc.arguments),
                    },
                }
                for tc in m.tool_calls
            ]
        else:
            d["content"] = m.content
        if m.role == "tool":
            if not m.tool_call_id:
                raise ValueError("tool messages require tool_call_id")
            d["tool_call_id"] = m.tool_call_id
            # OpenAI does NOT want `name` on tool messages (was deprecated)
        elif m.name:
            d["name"] = m.name
        out.append(d)
    return out


def to_anthropic(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """Convert to Anthropic's (system_string, messages_list) shape.

    Anthropic uses content blocks (text, tool_use, tool_result) inside
    messages, NOT a separate `tool` role. We translate appropriately.
    """
    system_parts: list[str] = [m.content for m in messages if m.role == "system"]
    convo: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    }
                )
            convo.append({"role": "assistant", "content": blocks})
        elif m.role == "tool":
            # Anthropic models tool results as a user message containing a
            # tool_result content block. Adjacent tool results merge into one
            # user message; we keep them separate for simplicity.
            convo.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id or "",
                            "content": m.content,
                        }
                    ],
                }
            )
        else:  # user
            convo.append({"role": "user", "content": m.content})
    return "\n\n".join(system_parts), convo


def _json_dumps(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return json.dumps({"_raw": str(obj)})


# Back-compat alias for older imports
_messages_to_dicts = to_openai_dicts
