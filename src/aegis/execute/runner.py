"""Stage 4 — Execute: run the agent loop using config FROM the synthesized harness.

The executor is intentionally a thin interpreter. Everything that varies per
task — the system prompt, max steps, max tokens per turn, temperature, tool
descriptions — comes from fields the LLM-generated harness module exposed
(or sensible defaults if the harness chose not to set them).

Multi-turn correctness: when the model emits tool calls we append the
assistant message *with* its ``tool_calls`` list, then a ``role="tool"``
message per call with the matching ``tool_call_id``. Both providers reject
the alternative.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aegis.core.goal import Goal
from aegis.execute.tool_registry import ToolRegistry
from aegis.providers.base import Message, Provider, ToolCall
from aegis.synthesize.sandbox import HarnessModule, SandboxError
from aegis.utils.json_io import extract_json

EXECUTE_INSTRUCTION_FRAME = """
Goal: {goal}

You may call ONLY these tools: {allowed_tools}.

Workflow:
  1. Call tools as needed to gather information.
  2. When you have enough to answer, emit a FINAL message with NO tool calls.
  3. The final message MUST be a single JSON object matching this schema:

{schema_block}

Rules:
  * Use ONLY tools from the allowed list above. Other calls will fail.
  * Your final answer MUST be raw JSON only — no prose wrapping, no markdown fences.
  * If a tool returns an error, retry sensibly or revise your plan — do not pretend it succeeded.
""".strip()


async def execute(
    goal: Goal,
    harness: HarnessModule,
    provider: Provider,
    tools: ToolRegistry,
) -> tuple[Any, list[dict[str, Any]], int, int]:
    """Run the agent loop using harness-defined config.

    Returns ``(validated_value_dict, tool_log, tokens_in, tokens_out)``.
    """
    allowed = harness.allowed_tools
    filtered = tools.subset(allowed)
    schema_json = json.dumps(harness.output_model.model_json_schema(), indent=2)
    schema_block = f"```json\n{schema_json}\n```"

    # System message = the harness's SYSTEM_PROMPT followed by the boilerplate
    # frame (schema + tool allowlist + workflow rules). The frame is fixed
    # because every harness needs the schema appended somewhere; the prefix
    # is the harness-supplied character.
    sys_text = (
        harness.system_prompt
        + "\n\n"
        + EXECUTE_INSTRUCTION_FRAME.format(
            goal=goal.description,
            allowed_tools=", ".join(allowed) or "(none — answer from prior knowledge)",
            schema_block=schema_block,
        )
    )
    messages: list[Message] = [Message.system(sys_text), Message.user(goal.description)]
    tool_call_log: list[dict[str, Any]] = []
    tokens_in = tokens_out = 0

    # Apply per-task tool-description overrides from the harness.
    provider_tools = []
    for spec in filtered.tools.values():
        pt = spec.to_provider_tool()
        if spec.name in harness.tool_overrides:
            pt = pt.model_copy(update={"description": harness.tool_overrides[spec.name]})
        provider_tools.append(pt)

    for step in range(harness.max_steps):
        response = await provider.complete(
            messages,
            tools=provider_tools or None,
            temperature=harness.temperature,
            max_tokens=harness.max_tokens_per_turn,
        )
        tokens_in += response.tokens_in
        tokens_out += response.tokens_out

        if response.tool_calls:
            messages.append(
                Message.assistant(content=response.text or "", tool_calls=response.tool_calls)
            )
            results = await asyncio.gather(
                *[_invoke_tool(call, filtered) for call in response.tool_calls]
            )
            for call, outcome in zip(response.tool_calls, results, strict=True):
                tool_call_log.append(
                    {
                        "step": step,
                        "name": call.name,
                        "arguments": call.arguments,
                        "ok": outcome["ok"],
                        "result_preview": _preview(outcome.get("result", outcome.get("error"))),
                    }
                )
                messages.append(
                    Message.tool_result(
                        tool_call_id=call.id,
                        name=call.name,
                        content=_jsonable(outcome),
                    )
                )
            continue

        # No tool call → expect the final JSON answer
        data = extract_json(response.text)
        if data is None:
            messages.append(Message.assistant(content=response.text))
            messages.append(
                Message.user(
                    "Your last reply was not valid JSON matching the schema. "
                    "Respond again with raw JSON only — no prose, no markdown fences."
                )
            )
            continue

        try:
            validated = harness.validate_output(data)
            return validated.model_dump(), tool_call_log, tokens_in, tokens_out
        except Exception as e:
            messages.append(Message.assistant(content=response.text))
            messages.append(
                Message.user(
                    f"Your output failed schema validation: {type(e).__name__}: {e}\n"
                    "Re-emit a corrected JSON object that conforms to the schema."
                )
            )

    raise SandboxError(f"Agent did not produce a valid output within {harness.max_steps} steps")


async def _invoke_tool(call: ToolCall, registry: ToolRegistry) -> dict[str, Any]:
    spec = registry.get(call.name)
    if spec is None:
        return {"ok": False, "error": f"Tool '{call.name}' not in allowed set"}
    try:
        result = await asyncio.to_thread(spec.fn, **call.arguments)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _preview(value: Any, *, max_len: int = 200) -> str:
    try:
        s = json.dumps(value, default=str)
    except (TypeError, ValueError):
        s = str(value)
    return s if len(s) <= max_len else s[:max_len] + "…"


def _jsonable(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, default=str)
    except (TypeError, ValueError):
        return json.dumps({"ok": payload.get("ok", False), "error": "unserializable"})
