"""Deterministic, multilingual keyword retrieval over the knowledge base.

No embeddings, no external NLP libraries: matches are found via a hand
built lexicon (English / Hindi / Hinglish aliases) plus a fallback match
on meaningful words already present in the shop data itself.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache

from meher_agent.config import Settings, settings as default_settings
from meher_agent.knowledge import KnowledgeBase, load_knowledge_base

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_DEVANAGARI_RANGE = re.compile(r"[ऀ-ॿ]")
_PUNCTUATION_RE = re.compile(r"[^\w\sऀ-ॿ]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")

ENGLISH_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "for",
    "of", "on", "in", "to", "and", "or", "with", "at", "by", "from",
    "this", "that", "we", "you", "your", "our", "it", "as", "if", "do",
    "does", "can", "will", "would", "please", "i", "my", "me", "us",
}

HINGLISH_STOPWORDS = {
    "hai", "hain", "ka", "ki", "ke", "ko", "se", "aur", "kya", "kyun",
    "kaise", "mera", "meri", "mere", "aap", "aapka", "aapki", "hoga",
    "hogi", "chahiye", "liye", "bhi", "toh", "to", "ho", "raha", "rahe",
}

STOPWORDS = ENGLISH_STOPWORDS | HINGLISH_STOPWORDS


def _is_devanagari_char(ch: str) -> bool:
    return bool(_DEVANAGARI_RANGE.match(ch))


def _normalize_roman_token(token: str) -> str:
    """Normalises common Hinglish spelling variants on a Roman-script token."""
    token = token.replace("oo", "u").replace("ee", "i").replace("aa", "a")
    token = re.sub(r"(.)\1+", r"\1", token)
    return token


def normalize(text: str) -> str:
    """Lowercases, strips punctuation, converts Devanagari digits to ASCII,
    and normalises Hinglish spelling variants on Roman-script tokens.
    Devanagari script itself is left as is."""
    text = text.translate(_DEVANAGARI_DIGITS)
    text = text.lower()
    text = _PUNCTUATION_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    tokens = []
    for token in text.split(" "):
        if not token:
            continue
        if any(_is_devanagari_char(ch) for ch in token) or token.isdigit():
            tokens.append(token)
        else:
            tokens.append(_normalize_roman_token(token))
    return " ".join(tokens)


@dataclass(frozen=True)
class Hit:
    source_id: str
    score: float
    matched_terms: list[str]


def _load_lexicon_raw(lexicon_path) -> dict:
    with open(lexicon_path, "rb") as f:
        return tomllib.load(f)


@lru_cache(maxsize=None)
def _load_lexicon_cached(settings_obj: Settings) -> dict[str, dict[str, list[str]]]:
    """Loads and normalises the lexicon: {section_type: {source_id: [normalized terms]}}.

    Product keys in the TOML file are bare SKUs (e.g. "KK-1000"); they are
    prefixed here to full source IDs ("prices.csv#KK-1000") so they line up
    with Product.source_id and with the data-derived keyword scoring.
    """
    raw = _load_lexicon_raw(settings_obj.paths.lexicon)
    normalized: dict[str, dict[str, list[str]]] = {"products": {}, "sections": {}}
    for sku, aliases in raw.get("products", {}).items():
        normalized["products"][f"prices.csv#{sku}"] = _normalize_aliases(aliases)
    for source_id, aliases in raw.get("sections", {}).items():
        normalized["sections"][source_id] = _normalize_aliases(aliases)
    return normalized


def _normalize_aliases(aliases: list[str]) -> list[str]:
    """Normalises lexicon aliases, dropping any that collapse to a bare
    stopword (e.g. the Hinglish-spelling normaliser turns "off" into "of",
    which would otherwise spuriously match the English stopword "of")."""
    result = []
    for alias in aliases:
        term = normalize(alias)
        if term and term not in STOPWORDS:
            result.append(term)
    return result


def load_lexicon(settings_obj: Settings | None = None) -> dict[str, dict[str, list[str]]]:
    return _load_lexicon_cached(settings_obj or default_settings)


def _meaningful_words(text: str) -> set[str]:
    normalized = normalize(text)
    return {w for w in normalized.split(" ") if w and w not in STOPWORDS and len(w) > 1}


@lru_cache(maxsize=None)
def _data_keywords_cached(settings_obj: Settings) -> dict[str, set[str]]:
    """Meaningful words derived from the shop data itself, per source ID."""
    kb = load_knowledge_base(settings_obj)
    keywords: dict[str, set[str]] = {}
    for product in kb.products:
        keywords[product.source_id] = _meaningful_words(product.item)
    for section in kb.sections:
        keywords[section.id] = _meaningful_words(section.heading) | _meaningful_words(section.text)
    return keywords


def _score_text(
    normalized_text: str,
    lexicon: dict[str, dict[str, list[str]]],
    data_keywords: dict[str, set[str]],
) -> dict[str, tuple[float, set[str]]]:
    """Scores a single normalized message/history turn against every source ID."""
    scores: dict[str, tuple[float, set[str]]] = {}

    def add(source_id: str, points: float, term: str) -> None:
        score, terms = scores.get(source_id, (0.0, set()))
        scores[source_id] = (score + points, terms | {term})

    padded_text = f" {normalized_text} "
    for group in ("products", "sections"):
        for source_id, terms in lexicon[group].items():
            for term in terms:
                if not term:
                    continue
                if " " in term:
                    if term in normalized_text:
                        add(source_id, 3.0, term)
                else:
                    if f" {term} " in padded_text:
                        add(source_id, 3.0, term)

    message_words = {w for w in normalized_text.split(" ") if w}
    for source_id, keywords in data_keywords.items():
        overlap = message_words & keywords
        for word in overlap:
            add(source_id, 1.0, word)

    return scores


def retrieve(
    message: str,
    history: list[str] | None = None,
    kb: KnowledgeBase | None = None,
    lexicon: dict[str, dict[str, list[str]]] | None = None,
    settings_obj: Settings | None = None,
) -> list[Hit]:
    settings_obj = settings_obj or default_settings
    kb = kb or load_knowledge_base(settings_obj)
    lexicon = lexicon or load_lexicon(settings_obj)
    data_keywords = _data_keywords_cached(settings_obj)
    history = history or []

    combined: dict[str, tuple[float, set[str]]] = {}

    def merge(scores: dict[str, tuple[float, set[str]]], weight: float) -> None:
        for source_id, (score, terms) in scores.items():
            existing_score, existing_terms = combined.get(source_id, (0.0, set()))
            combined[source_id] = (existing_score + score * weight, existing_terms | terms)

    merge(_score_text(normalize(message), lexicon, data_keywords), 1.0)
    for turn in history:
        merge(_score_text(normalize(turn), lexicon, data_keywords), settings_obj.retrieval.history_weight)

    hits = [
        Hit(source_id=source_id, score=score, matched_terms=sorted(terms))
        for source_id, (score, terms) in combined.items()
        if score >= settings_obj.retrieval.min_score
    ]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[: settings_obj.retrieval.top_k]
