import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.conversations import ConversationState, ConversationStore


def test_history_for_model_returns_all_when_fewer_than_n():
    state = ConversationState(conversation_id="c1")
    state.messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    assert state.history_for_model(10) == state.messages


def test_history_for_model_never_splits_tool_call_from_result():
    state = ConversationState(conversation_id="c1")
    state.messages = [
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t1", "type": "function", "function": {}}]},
        {"role": "tool", "tool_call_id": "t1", "content": "result"},
        {"role": "assistant", "content": "final reply 1"},
        {"role": "user", "content": "turn 2"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t2", "type": "function", "function": {}}]},
        {"role": "tool", "tool_call_id": "t2", "content": "result 2"},
        {"role": "assistant", "content": "final reply 2"},
    ]
    # n=3 would naively cut into the middle of turn 2's tool call/result pair.
    history = state.history_for_model(3)
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "turn 2"
    # No 'tool' message appears without its preceding assistant tool_call.
    for i, msg in enumerate(history):
        if msg["role"] == "tool":
            assert history[i - 1]["role"] == "assistant"
            assert "tool_calls" in history[i - 1]


def test_conversation_store_get_or_create_persists():
    store = ConversationStore()
    state1 = store.get_or_create("c1")
    state1.turn_count = 5
    state2 = store.get_or_create("c1")
    assert state2.turn_count == 5


def test_conversation_store_separate_conversations():
    store = ConversationStore()
    a = store.get_or_create("a")
    b = store.get_or_create("b")
    assert a is not b
