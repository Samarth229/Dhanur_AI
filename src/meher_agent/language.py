"""Language detection (English / Hindi / Hinglish) and digit normalisation.

Deterministic, no external NLP libraries. The Hinglish marker word list is
data (src/meher_agent/resources/lexicon.toml), not code.
"""
from __future__ import annotations

import re
import tomllib
from functools import lru_cache

from meher_agent.config import Settings, settings as default_settings

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_DEVANAGARI_LETTER_RE = re.compile(r"[ऀ-ॿ]")
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")
_WORD_RE = re.compile(r"[\w']+", re.UNICODE)

DEVANAGARI_RATIO_THRESHOLD = 0.3
HINGLISH_MARKER_COUNT_THRESHOLD = 2
NEUTRAL_MAX_TOKENS = 2


def normalize_digits(text: str) -> str:
    """Converts Devanagari digits ०-९ to ASCII 0-9."""
    return text.translate(_DEVANAGARI_DIGITS)


@lru_cache(maxsize=None)
def _load_language_words(lexicon_path) -> tuple[set[str], set[str]]:
    with open(lexicon_path, "rb") as f:
        raw = tomllib.load(f)
    language = raw.get("language", {})
    markers = {m.lower() for m in language.get("hinglish_markers", [])}
    english_function_words = {w.lower() for w in language.get("english_function_words", [])}
    return markers, english_function_words


def _load_markers(settings_obj: Settings) -> set[str]:
    markers, _ = _load_language_words(settings_obj.paths.lexicon)
    return markers


def _load_english_function_words(settings_obj: Settings) -> set[str]:
    _, english_function_words = _load_language_words(settings_obj.paths.lexicon)
    return english_function_words


def detect_language(
    text: str, previous: str | None = None, *, settings_obj: Settings | None = None
) -> str:
    """Returns "hi", "hinglish" or "en"."""
    settings_obj = settings_obj or default_settings
    text = normalize_digits(text)

    letters = _DEVANAGARI_LETTER_RE.findall(text) + _LATIN_LETTER_RE.findall(text)
    if letters:
        devanagari_count = sum(1 for ch in letters if _DEVANAGARI_LETTER_RE.match(ch))
        if devanagari_count / len(letters) >= DEVANAGARI_RATIO_THRESHOLD:
            return "hi"

    tokens = _WORD_RE.findall(text)
    words = [t.lower() for t in tokens]

    markers = _load_markers(settings_obj)
    marker_count = sum(1 for w in words if w in markers)
    if marker_count >= HINGLISH_MARKER_COUNT_THRESHOLD:
        return "hinglish"
    if marker_count == 1:
        english_function_words = _load_english_function_words(settings_obj)
        has_english_function_word = any(w in english_function_words for w in words)
        if not has_english_function_word:
            return "hinglish"

    if len(tokens) <= NEUTRAL_MAX_TOKENS and previous is not None:
        return previous

    return "en"
