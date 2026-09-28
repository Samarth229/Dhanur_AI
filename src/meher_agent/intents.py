"""Deterministic intent detection from data-driven word lists.

Independent of the model: used by the agent to catch cases where the
model recognises the customer's intent in its reply text but forgets to
call the matching tool (e.g. a complaint without calling escalate).
"""
from __future__ import annotations

import tomllib
from functools import lru_cache

from meher_agent.config import Settings, settings as default_settings
from meher_agent.retrieval import normalize


def _match_word(term: str, text: str) -> bool:
    if not term:
        return False
    if " " in term:
        return term in text
    return f" {term} " in f" {text} "


@lru_cache(maxsize=None)
def _load_intents(lexicon_path) -> dict[str, list[str]]:
    with open(lexicon_path, "rb") as f:
        raw = tomllib.load(f)
    intents = raw.get("intents", {})
    return {name: [normalize(w) for w in words] for name, words in intents.items()}


def detect_intents(text: str, settings_obj: Settings | None = None) -> set[str]:
    settings_obj = settings_obj or default_settings
    intents = _load_intents(settings_obj.paths.lexicon)
    normalized = normalize(text)
    return {name for name, words in intents.items() if any(_match_word(w, normalized) for w in words)}
