"""Builds the system prompt, per-turn language instruction, and loads
fixed reply templates. Keeps the static system prompt byte-identical
across turns (only {today} and {shop_data} vary within a single process
run) so an LLM server can cache the shared prefix.
"""
from __future__ import annotations

import re
import tomllib
from datetime import date
from functools import lru_cache

from meher_agent.canary import CANARY
from meher_agent.config import Settings, settings as default_settings
from meher_agent.knowledge import KnowledgeBase, load_knowledge_base

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

LANGUAGE_INSTRUCTIONS = {
    "en": "Reply in English.",
    "hi": "Reply in Hindi using Devanagari script. Keep product names, ₹ amounts and digits 0-9 as they are.",
    "hinglish": "Reply in Hinglish (Hindi written in Roman/English letters, like the customer). Use digits 0-9.",
}


@lru_cache(maxsize=None)
def _load_prompt_template(path) -> str:
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _load_templates(path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _find_support_email(kb: KnowledgeBase) -> str:
    section = kb.get_section("business.md#how-to-order")
    if section:
        match = _EMAIL_RE.search(section.text)
        if match:
            return match.group(0)
    return "orders@meher-sweets.example"


def build_system_prompt(settings_obj: Settings | None = None, today: date | None = None) -> str:
    settings_obj = settings_obj or default_settings
    kb = load_knowledge_base(settings_obj)
    template = _load_prompt_template(settings_obj.paths.system_prompt)
    today = today or date.today()
    policy = settings_obj.policy

    return template.format(
        canary=CANARY,
        today=today.isoformat(),
        shop_data=kb.render_full_context(),
        giftbox_discount_pct=policy.giftbox_discount_pct,
        giftbox_discount_min_boxes=policy.giftbox_discount_min_boxes,
        bulk_notice_days=policy.bulk_notice_days,
        bulk_advance_pct=policy.bulk_advance_pct,
        support_email=_find_support_email(kb),
    )


def language_instruction(language: str) -> str:
    return LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["en"])


def get_template(name: str, language: str, settings_obj: Settings | None = None, **kwargs) -> str:
    settings_obj = settings_obj or default_settings
    templates = _load_templates(settings_obj.paths.templates)
    entry = templates[name]
    text = entry.get(language, entry["en"])
    if kwargs:
        text = text.format(**kwargs)
    return text
