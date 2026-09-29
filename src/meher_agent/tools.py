"""The three tools the model can call: calculate_order, save_lead, escalate.

Arguments are validated before anything runs. Nothing here ever raises:
every failure mode becomes a ToolResult(ok=False, ...) with an "ERROR:"
message the model can act on.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import re

from meher_agent.config import Settings
from meher_agent.knowledge import KnowledgeBase
from meher_agent.pricing import PricingError, _families, family_lexicon_aliases, quote_order, resolve_item
from meher_agent.privacy import find_emails, find_phones
from meher_agent.retrieval import normalize as normalize_for_matching
from meher_agent.stores import EscalationStore, LeadStore
from meher_agent.validation import (
    ValidationError,
    normalize_date,
    normalize_email,
    normalize_name,
    normalize_phone,
)

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
_NAME_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_DISTANCE_MENTION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:km|kilometre|kilometer|किलोमीटर)", re.IGNORECASE
)
_PACK_MENTION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:pack|packet|पैक|dabba)", re.IGNORECASE
)

logger = logging.getLogger(__name__)

_MISSING_VALUES = {"", "null", "none", "n/a", "unknown", "-"}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "calculate_order",
            "description": (
                "Compute exact prices and totals. ALWAYS call this for any total, "
                "subtotal, discount, delivery charge or multi-item price. Never do "
                "arithmetic yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "The items in the order.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item": {
                                    "type": "string",
                                    "description": "SKU or product name.",
                                },
                                "amount": {"type": "number"},
                                "unit": {
                                    "type": "string",
                                    "enum": ["kg", "g", "piece", "box", "pack"],
                                    "description": (
                                        "If the customer said pack/packet/पैक/dabba, use "
                                        "'pack' (a whole pack of that product's size), NOT "
                                        "'kg' -- packs are not the same as kilograms. If "
                                        "they said kilo/किलो/kilogram, use 'kg'."
                                    ),
                                },
                            },
                            "required": ["item", "amount", "unit"],
                        },
                    },
                    "distance_km": {
                        "type": "number",
                        "description": "Only if the customer said it.",
                    },
                    "delivery_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_lead",
            "description": (
                "Save a customer's contact details when they want a wedding, custom "
                "or large order and have given a name and a phone number or email."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "need": {
                        "type": "string",
                        "description": "A short description of what they want.",
                    },
                    "phone": {"type": "string"},
                    "email": {"type": "string"},
                    "quantity": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["name", "need"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate",
            "description": (
                "Hand the conversation to the human team. Use ONLY for: complaints, "
                "damaged deliveries, the customer asking for a person, or the "
                "customer accepting your offer to pass on an unanswered question. "
                "Do NOT use for out-of-scope requests (homework, coding, general "
                "knowledge, other businesses) -- decline those yourself in one "
                "sentence and call no tool at all. Do NOT use for questions you can "
                "answer from SHOP DATA."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    },
]


class ToolArgumentError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class ToolContext:
    conversation_id: str
    kb: KnowledgeBase
    lexicon: Any
    settings: Settings
    lead_store: LeadStore
    escalation_store: EscalationStore
    today: date
    customer_messages: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    ok: bool
    name: str
    content: str
    action: dict[str, Any] | None
    handoff: bool
    data: Any = None


def _clean_optional(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in _MISSING_VALUES:
        return None
    return value


def _next_occurrence(target: date, today: date) -> date:
    """The next real calendar date with target's month/day, on or after today."""
    year = today.year
    while True:
        try:
            candidate = date(year, target.month, target.day)
        except ValueError:
            year += 1
            continue
        if candidate >= today:
            return candidate
        year += 1


def _parse_raw_arguments(raw_arguments: str | dict) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    try:
        parsed = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError):
        raise ToolArgumentError("arguments were not valid JSON.")
    if not isinstance(parsed, dict):
        raise ToolArgumentError("arguments must be a JSON object.")
    return parsed


def _customer_text(ctx: ToolContext) -> str:
    return normalize_for_matching(" ".join(ctx.customer_messages))


def _item_grounded(item_name: str, ctx: ToolContext) -> bool:
    """Fix 9a: the resolved product's family must have at least one alias
    (or, if the customer typed a SKU directly, that SKU) the customer
    actually said somewhere in this conversation."""
    try:
        family, _ = resolve_item(item_name, ctx.kb, ctx.settings)
    except PricingError:
        return True  # NOT_ON_MENU/AMBIGUOUS are reported separately by quote_order itself.
    aliases = family_lexicon_aliases(family, ctx.settings)
    customer_text = _customer_text(ctx)
    if any(alias and alias in customer_text for alias in aliases):
        return True
    raw_customer_text = " ".join(ctx.customer_messages).upper()
    return any(product.sku.upper() in raw_customer_text for product in family.products)


def _mentioned_distance_km(ctx: ToolContext) -> float | None:
    """Fix 9b: the last distance (in km) the customer actually stated."""
    matches = _DISTANCE_MENTION_RE.findall(" ".join(ctx.customer_messages))
    return float(matches[-1]) if matches else None


def _mentioned_pack_quantities_for_item(item_name: str, ctx: ToolContext) -> set[float]:
    """Fix 9c: quantities the customer attached to a pack word (पैक/pack/
    packet/dabba) for THIS specific item, e.g. "2 पैक" -> {2.0}.

    A pack number only counts if the message that mentions it doesn't also
    mention a *different* product family -- otherwise "3 packs of soan
    papdi" in one turn would wrongly block an unrelated later order of
    "3 kg" of, say, motichoor laddoo just because both happen to use the
    number 3 (found via manual multi-turn chat-page testing, turn 8/10 of
    the hotfix transcript in reports/failure_log.md). The item name and its
    pack quantity are still allowed to be split across separate turns
    (e.g. "rasmalai?" then "2 pack chahiye"), as long as no other product
    was named in between."""
    try:
        this_family, _ = resolve_item(item_name, ctx.kb, ctx.settings)
    except PricingError:
        this_family = None

    other_aliases: set[str] = set()
    if this_family is not None:
        this_family_names = {this_family.name}
    else:
        this_family_names = set()
    for family in _families(ctx.settings):
        if family.name in this_family_names:
            continue
        other_aliases |= family_lexicon_aliases(family, ctx.settings)

    matches: set[float] = set()
    for msg in ctx.customer_messages:
        normalized = normalize_for_matching(msg)
        mentions_other_product = any(alias and alias in normalized for alias in other_aliases)
        if mentions_other_product:
            continue
        matches.update(float(m) for m in _PACK_MENTION_RE.findall(msg))
    return matches


def _handle_calculate_order(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    items_raw = args.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise ToolArgumentError("items must be a non-empty list of {item, amount, unit}.")

    items = []
    for entry in items_raw:
        if not isinstance(entry, dict):
            raise ToolArgumentError("each item must be an object with item, amount and unit.")
        item_name = _clean_optional(entry.get("item"))
        if not item_name:
            raise ToolArgumentError("each item needs a non-empty 'item' name.")
        try:
            amount = float(entry.get("amount"))
        except (TypeError, ValueError):
            raise ToolArgumentError(f"amount must be a number, got {entry.get('amount')!r}.")
        unit = _clean_optional(entry.get("unit"))
        if not unit:
            raise ToolArgumentError("each item needs a 'unit'.")

        if not _item_grounded(item_name, ctx):
            raise ToolArgumentError(
                f"the customer did not ask for {item_name}. Only price items the customer asked for."
            )

        pack_quantities = _mentioned_pack_quantities_for_item(item_name, ctx)
        if unit.strip().lower() in {"kg", "g"} and amount in pack_quantities:
            raise ToolArgumentError(
                f"the customer asked for {amount:g} packs; use unit 'pack', not '{unit}'."
            )

        items.append({"item": item_name, "amount": amount, "unit": unit})

    distance_km = _clean_optional(args.get("distance_km"))
    if distance_km is not None:
        try:
            distance_km = float(distance_km)
        except (TypeError, ValueError):
            raise ToolArgumentError(f"distance_km must be a number, got {distance_km!r}.")

    mentioned_distance = _mentioned_distance_km(ctx)
    if mentioned_distance is not None and distance_km != mentioned_distance:
        raise ToolArgumentError(
            f"the customer said delivery is {mentioned_distance:g} km away; use "
            f"distance_km={mentioned_distance:g}."
        )

    delivery_date = _clean_optional(args.get("delivery_date"))
    if delivery_date is not None:
        delivery_date = normalize_date(str(delivery_date)).isoformat()

    quote = quote_order(
        items,
        distance_km=distance_km,
        delivery_date=delivery_date,
        today=ctx.today,
        kb=ctx.kb,
        settings_obj=ctx.settings,
    )
    content = quote.to_tool_text() + "\nUse ONLY these amounts in your reply."
    return ToolResult(ok=True, name="calculate_order", content=content, action=None, handoff=False, data=quote)


def _grounded_phones(customer_messages: list[str]) -> set[str]:
    found = set()
    for msg in customer_messages:
        found.update(find_phones(msg))
    return found


def _grounded_emails(customer_messages: list[str]) -> set[str]:
    found = set()
    for msg in customer_messages:
        for candidate in find_emails(msg):
            try:
                found.add(normalize_email(candidate))
            except ValidationError:
                continue
    return found


def _ground_or_reject(field_name: str, value: str | None, grounded: set[str]) -> str | None:
    """Fix 5a: the model's phone/email must match something the customer
    actually typed. If it doesn't, but exactly one grounded value exists,
    use that instead (the model may have mis-copied it); if none exists,
    reject rather than save a value the customer never gave."""
    if value is None:
        return None
    if value in grounded:
        return value
    if len(grounded) == 1:
        return next(iter(grounded))
    raise ToolArgumentError(f"that {field_name} was not given by the customer; ask for it.")


def _name_grounded(name: str, customer_messages: list[str]) -> bool:
    """Fix 5b: every token of the name must appear as a whole word in what
    the customer typed, so the model can't invent a name. Skipped when any
    customer message contains Devanagari, since the model may transliterate
    a Hindi name into the Roman-script `name` argument."""
    if any(_DEVANAGARI_RE.search(m) for m in customer_messages):
        return True
    combined = " ".join(customer_messages).casefold()
    # Replace punctuation with spaces (not just casefold) so a name right
    # before a comma, period or @ still matches as a whole word.
    combined_clean = re.sub(r"[^\w\s]", " ", combined, flags=re.UNICODE)
    padded = f" {combined_clean} "
    tokens = _NAME_TOKEN_RE.findall(name.casefold())
    if not tokens:
        return True
    return all(f" {tok} " in padded for tok in tokens)


def _handle_save_lead(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    name_raw = _clean_optional(args.get("name"))
    if not name_raw:
        raise ToolArgumentError("name is required.")
    name = normalize_name(str(name_raw))
    if not _name_grounded(name, ctx.customer_messages):
        raise ToolArgumentError("that name was not given by the customer; ask for their name.")

    need_raw = _clean_optional(args.get("need"))
    if not need_raw:
        raise ToolArgumentError("need is required.")
    need = str(need_raw).strip()
    if not (1 <= len(need) <= 300):
        raise ToolArgumentError("need must be between 1 and 300 characters.")

    phone_raw = _clean_optional(args.get("phone"))
    phone = normalize_phone(str(phone_raw)) if phone_raw is not None else None
    phone = _ground_or_reject("phone", phone, _grounded_phones(ctx.customer_messages))

    email_raw = _clean_optional(args.get("email"))
    email = normalize_email(str(email_raw)) if email_raw is not None else None
    email = _ground_or_reject("email", email, _grounded_emails(ctx.customer_messages))

    if phone is None and email is None:
        raise ToolArgumentError("At least a phone number or an email address is required.")

    quantity_raw = _clean_optional(args.get("quantity"))
    quantity = None
    if quantity_raw is not None:
        quantity = str(quantity_raw).strip()
        if len(quantity) > 100:
            raise ToolArgumentError("quantity must be at most 100 characters.")

    date_raw = _clean_optional(args.get("date"))
    date_value = None
    if date_raw is not None:
        parsed = normalize_date(str(date_raw))
        if parsed < ctx.today:
            hint = _next_occurrence(parsed, ctx.today)
            raise ToolArgumentError(
                f"date {parsed.isoformat()} is in the past. If the customer meant "
                f"the upcoming {parsed.day} {parsed.strftime('%B')}, use {hint.isoformat()}."
            )
        date_value = parsed.isoformat()

    fields = {
        "name": name,
        "need": need,
        "phone": phone,
        "email": email,
        "quantity": quantity,
        "date": date_value,
    }
    lead, created = ctx.lead_store.upsert(ctx.conversation_id, fields)
    status = "saved" if created else "updated"

    policy = ctx.settings.policy
    content = (
        f"Tell the customer: their details have been {status} and the team will call or email "
        "them back about this. Do not say the order is confirmed. If it is a bulk order (more "
        f"than {policy.bulk_sweets_kg_over:g} kg of sweets or more than {policy.bulk_giftboxes_over:g} "
        f"gift boxes), mention that it needs {policy.bulk_notice_days:g} days' notice and a "
        f"{policy.bulk_advance_pct:g}% advance."
    )
    action = {"type": "save_lead", "args": fields}
    return ToolResult(ok=True, name="save_lead", content=content, action=action, handoff=False, data=lead)


def _handle_escalate(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    reason_raw = _clean_optional(args.get("reason"))
    if not reason_raw:
        raise ToolArgumentError("reason is required.")
    reason = str(reason_raw).strip()
    if not (1 <= len(reason) <= 500):
        raise ToolArgumentError("reason must be between 1 and 500 characters.")

    ctx.escalation_store.add(ctx.conversation_id, reason)

    content = (
        "Tell the customer, in their language, that the team will get back to them "
        "by email within one working day. If this is about a damaged delivery, ask "
        "them for a photo and note that damage must be reported within 2 hours of "
        "delivery. Apologise once only."
    )
    action = {"type": "escalate", "args": {"reason": reason}}
    return ToolResult(ok=True, name="escalate", content=content, action=action, handoff=True, data=None)


_HANDLERS = {
    "calculate_order": _handle_calculate_order,
    "save_lead": _handle_save_lead,
    "escalate": _handle_escalate,
}


def execute_tool(name: str, raw_arguments: str | dict, ctx: ToolContext) -> ToolResult:
    if name not in _HANDLERS:
        return ToolResult(
            ok=False, name=name, content=f"ERROR: unknown tool '{name}'.", action=None, handoff=False
        )

    try:
        args = _parse_raw_arguments(raw_arguments)
        return _HANDLERS[name](args, ctx)
    except (ToolArgumentError, ValidationError, PricingError) as exc:
        message = exc.message
        suggestions = getattr(exc, "suggestions", None)
        if suggestions:
            message = f"{message} Options: {'; '.join(suggestions)}"
        return ToolResult(ok=False, name=name, content=f"ERROR: {message}", action=None, handoff=False)
    except Exception:
        logger.exception("Unexpected error executing tool '%s'", name)
        return ToolResult(
            ok=False,
            name=name,
            content="ERROR: something went wrong processing this request. Please try again "
            "or ask the team for help.",
            action=None,
            handoff=False,
        )
