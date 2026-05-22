"""Multi-turn message serialization — the bug that broke real-LLM use in v0.0."""

from __future__ import annotations

import json

import pytest

from aegis.providers.base import Message, ToolCall, to_anthropic, to_openai_dicts


@pytest.fixture
def multi_turn_messages() -> list[Message]:
    """A realistic multi-turn conversation with a tool call + reply."""
    return [
        Message.system("You are a helpful agent."),
        Message.user("What is the weather in NYC?"),
        Message.assistant(
            content="",
            tool_calls=[ToolCall(id="call_1", name="get_weather", arguments={"city": "NYC"})],
        ),
        Message.tool_result(tool_call_id="call_1", name="get_weather", content='{"temp_f": 72}'),
        Message.assistant(content="It is 72°F in NYC."),
    ]


class TestOpenAISerialization:
    def test_assistant_tool_call_dict_shape(self, multi_turn_messages):
        dicts = to_openai_dicts(multi_turn_messages)
        # 5 messages → 5 dicts
        assert len(dicts) == 5

        # Assistant tool-call message MUST contain a `tool_calls` list,
        # not just `content`. This was the v0.0 bug.
        assistant_call = dicts[2]
        assert assistant_call["role"] == "assistant"
        assert "tool_calls" in assistant_call
        tc = assistant_call["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "get_weather"
        # arguments must be a JSON string, not a dict
        assert isinstance(tc["function"]["arguments"], str)
        assert json.loads(tc["function"]["arguments"]) == {"city": "NYC"}

    def test_tool_message_has_tool_call_id(self, multi_turn_messages):
        dicts = to_openai_dicts(multi_turn_messages)
        tool_msg = dicts[3]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_1"
        # `name` is NOT carried on tool messages (deprecated)
        assert "name" not in tool_msg

    def test_tool_message_without_id_raises(self):
        bad = [Message(role="tool", content="x", tool_call_id=None)]
        with pytest.raises(ValueError, match="tool_call_id"):
            to_openai_dicts(bad)

    def test_assistant_no_tool_calls_omits_field(self):
        msgs = [Message.assistant(content="hello")]
        dicts = to_openai_dicts(msgs)
        assert dicts[0] == {"role": "assistant", "content": "hello"}


class TestAnthropicSerialization:
    def test_system_extracted_and_joined(self, multi_turn_messages):
        system, _convo = to_anthropic(multi_turn_messages)
        assert "helpful agent" in system

    def test_assistant_tool_use_block_shape(self, multi_turn_messages):
        _, convo = to_anthropic(multi_turn_messages)
        # 4 non-system messages
        assert len(convo) == 4

        # Assistant with tool call → content blocks with text + tool_use
        assistant_call = convo[1]
        assert assistant_call["role"] == "assistant"
        blocks = assistant_call["content"]
        assert isinstance(blocks, list)
        tool_use = next(b for b in blocks if b["type"] == "tool_use")
        assert tool_use["id"] == "call_1"
        assert tool_use["name"] == "get_weather"
        assert tool_use["input"] == {"city": "NYC"}

    def test_tool_result_is_user_message_with_block(self, multi_turn_messages):
        _, convo = to_anthropic(multi_turn_messages)
        tool_result = convo[2]
        assert tool_result["role"] == "user"
        assert tool_result["content"][0]["type"] == "tool_result"
        assert tool_result["content"][0]["tool_use_id"] == "call_1"


def test_message_factory_helpers():
    """The factory methods produce well-formed messages."""
    s = Message.system("sys")
    assert s.role == "system"
    u = Message.user("hi")
    assert u.role == "user"
    a = Message.assistant("ans", tool_calls=[ToolCall(id="x", name="t", arguments={})])
    assert a.role == "assistant"
    assert a.tool_calls[0].id == "x"
    t = Message.tool_result("x", "t", '{"ok":1}')
    assert t.role == "tool"
    assert t.tool_call_id == "x"
