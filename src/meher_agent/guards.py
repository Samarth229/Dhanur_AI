"""Reply guards (amount, percentage, privacy, prompt-leak, empty, length)
and source-ID assembly for the agent's replies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from meher_agent.amounts import extract_rupee_amounts_strict
from meher_agent.canary import CANARY
from meher_agent.config import Settings
from meher_agent.knowledge import KnowledgeBase
from meher_agent.language import normalize_digits
from meher_agent.privacy import find_emails, find_phones
from meher_agent.retrieval import Hit, load_lexicon
from meher_agent.retrieval import normalize as normalize_for_matching

_PERCENT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent|प्रतिशत|pratishat)",
    re.IGNORECASE,
)


def base_allowed_amounts(kb: KnowledgeBase, settings: Settings) -> set[float]:
    """Product prices plus the policy amounts a reply may legitimately mention."""
    amounts = {float(p.price_inr) for p in kb.products}
    amounts.add(float(settings.policy.free_delivery_min_inr))
    amounts.add(float(settings.policy.delivery_fee_inr))
    amounts.add(float(settings.policy.cod_max_inr))
    return amounts


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    cleaned_text: str = ""


def check_reply(
    text: str,
    allowed_amounts: set[float],
    settings: Settings,
    *,
    support_email: str = "orders@meher-sweets.example",
    disclosure: str = "",
) -> GuardResult:
    problems: list[str] = []
    cleaned = normalize_digits(text)

    # 1-2. Amount guard.
    found_amounts = extract_rupee_amounts_strict(cleaned)
    disallowed = sorted({a for a in found_amounts if a not in allowed_amounts})
    if disallowed:
        problems.append(
            "disallowed amount(s): " + ", ".join(f"₹{a:g}" for a in disallowed)
        )

    # 3. Percentage guard.
    for match in _PERCENT_RE.finditer(cleaned):
        pct = float(match.group(1))
        if pct not in settings.agent.allowed_percentages:
            problems.append(f"disallowed percentage: {pct:g}%")

    # 4. Privacy guard.
    leaked_emails = [e for e in find_emails(cleaned) if e.lower() != support_email.lower()]
    leaked_phones = find_phones(cleaned)
    if leaked_emails or leaked_phones:
        problems.append("reply contains a contact detail that should have been withheld")

    # 5. Prompt-leak (canary) guard.
    if CANARY in cleaned:
        problems.append("reply leaked the system prompt canary")

    # 6. Empty-after-cleaning guard.
    if not cleaned.strip():
        problems.append("reply is empty")

    # 7. Length trim (never fails the guard, just trims).
    max_chars = settings.reply.max_chars
    budget = max_chars - len(disclosure)
    if budget > 0 and len(cleaned) > budget:
        cleaned = _trim_to_sentence_boundary(cleaned, budget)

    return GuardResult(ok=not problems, problems=problems, cleaned_text=cleaned)


def _trim_to_sentence_boundary(text: str, budget: int) -> str:
    truncated = text[:budget]
    for boundary in (". ", "! ", "? ", "\n"):
        idx = truncated.rfind(boundary)
        if idx != -1:
            return truncated[: idx + 1].strip()
    return truncated.strip()


def build_sources(
    reply_text: str,
    quote,
    hits: list[Hit],
    kb: KnowledgeBase,
    settings: Settings,
    action_types: set[str],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def add(source_id: str) -> None:
        if source_id in kb.valid_source_ids and source_id not in seen:
            seen.add(source_id)
            ordered.append(source_id)

    if quote is not None:
        for source_id in quote.source_ids:
            add(source_id)

    for hit in hits:
        add(hit.source_id)

    lexicon = load_lexicon(settings)
    normalized_reply = normalize_for_matching(reply_text)
    for source_id, aliases in lexicon.get("products", {}).items():
        for alias in aliases:
            if alias and alias in normalized_reply:
                add(source_id)
                break

    if "escalate" in action_types:
        add("policies.md#complaints")
    if "save_lead" in action_types:
        add("policies.md#wedding-and-custom-orders")

    return ordered[: settings.agent.max_sources]
