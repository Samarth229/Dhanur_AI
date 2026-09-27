import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.llm import _extract_text_tool_call, _strip_think

KNOWN_TOOLS = {"calculate_order", "save_lead", "escalate"}


def test_strip_think_removes_block():
    text = "<think>internal reasoning here</think>Hello there!"
    assert _strip_think(text) == "Hello there!"


def test_strip_think_no_block_unchanged():
    assert _strip_think("Just a normal reply.") == "Just a normal reply."


def test_strip_think_case_insensitive_and_multiline():
    text = "<THINK>\nline one\nline two\n</THINK>Final answer."
    assert _strip_think(text) == "Final answer."


def test_extract_tool_call_tag_format():
    content = '<tool_call>{"name": "escalate", "arguments": {"reason": "test"}}</tool_call>'
    remaining, call = _extract_text_tool_call(content, KNOWN_TOOLS)
    assert call is not None
    assert call.name == "escalate"
    assert remaining == ""


def test_extract_bare_json_tool_call():
    content = 'Sure, let me do that. {"name": "escalate", "arguments": {"reason": "test"}}'
    remaining, call = _extract_text_tool_call(content, KNOWN_TOOLS)
    assert call is not None
    assert call.name == "escalate"


def test_extract_no_tool_call_when_name_unknown():
    content = '{"name": "not_a_real_tool", "arguments": {}}'
    remaining, call = _extract_text_tool_call(content, KNOWN_TOOLS)
    assert call is None
    assert remaining == content


def test_extract_no_tool_call_in_plain_text():
    content = "Just a normal reply with no tool call."
    remaining, call = _extract_text_tool_call(content, KNOWN_TOOLS)
    assert call is None
    assert remaining == content
