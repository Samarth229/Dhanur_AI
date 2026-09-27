"""In-memory conversation state, keyed by conversation_id."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationState:
    conversation_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    language: str | None = None
    turn_count: int = 0
    allowed_amounts: set[float] = field(default_factory=set)
    handoff: bool = False

    def history_for_model(self, n: int) -> list[dict[str, Any]]:
        """The last n messages, extended backward so a tool result is never
        separated from the assistant tool_call that produced it."""
        if len(self.messages) <= n:
            return list(self.messages)

        start = len(self.messages) - n
        # Walk back to the nearest preceding user-message boundary so we
        # never start mid tool-call/tool-result sequence.
        while start > 0 and self.messages[start]["role"] != "user":
            start -= 1
        return list(self.messages[start:])


class ConversationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._conversations: dict[str, ConversationState] = {}

    def get_or_create(self, conversation_id: str) -> ConversationState:
        with self._lock:
            state = self._conversations.get(conversation_id)
            if state is None:
                state = ConversationState(conversation_id=conversation_id)
                self._conversations[conversation_id] = state
            return state
