"""Deterministic pricing engine for the Meher Sweets assistant.

The model never does arithmetic: it calls calculate_order (Part 4) with a
list of {item, amount, unit} dicts, and this module resolves the item
against the knowledge base, picks the cheapest exact combination of packs,
and applies every business rule from data/policies.md. Pure Python, no
LLM calls, no randomness.
"""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache

from meher_agent.config import Settings, settings as default_settings
from meher_agent.knowledge import KnowledgeBase, Product, load_knowledge_base
from meher_agent.retrieval import normalize

WEIGHT_UNITS = {"kg": 1000, "kilo": 1000, "kilogram": 1000, "g": 1, "gm": 1, "gram": 1}
PIECE_UNITS = {"piece", "pc", "pcs", "nos"}
BOX_UNITS = {"box", "boxes"}
PACK_UNITS = {"pack", "packet", "पैक", "dabba"}

SWEET_TYPES = {"dry sweet", "milk sweet"}
GIFT_BOX_SKUS = {"GBS", "GBL"}


class PricingError(Exception):
    def __init__(self, code: str, message: str, suggestions: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestions = suggestions or []


def round_half_up(value) -> int:
    """Rounds money to the nearest whole rupee, half rounds up (not banker's rounding)."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_inr(n: int) -> str:
    """Formats an integer with Indian digit grouping: 3850 -> '3,850', 100000 -> '1,00,000'."""
    negative = n < 0
    n = abs(int(n))
    s = str(n)
    if len(s) <= 3:
        result = s
    else:
        last_three = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        result = ",".join(groups) + "," + last_three
    return f"-{result}" if negative else result


@dataclass(frozen=True)
class ProductFamily:
    name: str
    products: list[Product]

    @property
    def unit_kind(self) -> str:
        return self.products[0].pack_unit


@lru_cache(maxsize=None)
def _load_lexicon_products(lexicon_path) -> dict[str, list[str]]:
    """Loads {sku: [normalized aliases]} straight from the lexicon TOML file."""
    with open(lexicon_path, "rb") as f:
        raw = tomllib.load(f)
    result: dict[str, list[str]] = {}
    for sku, aliases in raw.get("products", {}).items():
        result[sku] = [normalize(alias) for alias in aliases]
    return result


@lru_cache(maxsize=None)
def _load_sizes(lexicon_path) -> dict[str, set[str]]:
    """Loads {size_category: {normalized size words}} for disambiguating
    product families that differ only by size (e.g. small vs large gift
    boxes) when their other aliases tie."""
    with open(lexicon_path, "rb") as f:
        raw = tomllib.load(f)
    return {
        category: {normalize(w) for w in words}
        for category, words in raw.get("sizes", {}).items()
    }


@lru_cache(maxsize=None)
def _families(settings_obj: Settings) -> list[ProductFamily]:
    kb = load_knowledge_base(settings_obj)
    by_item: dict[str, list[Product]] = {}
    for product in kb.products:
        by_item.setdefault(product.item, []).append(product)
    return [ProductFamily(name=item, products=products) for item, products in by_item.items()]


def _family_for_sku(settings_obj: Settings, sku: str) -> ProductFamily:
    for family in _families(settings_obj):
        for product in family.products:
            if product.sku == sku:
                return family
    raise KeyError(sku)


def _alias_word_set(alias: str) -> frozenset[str]:
    return frozenset(w for w in alias.split(" ") if w)


def _resolve_item(
    item_text: str, kb: KnowledgeBase, settings_obj: Settings
) -> tuple[ProductFamily, Product | None]:
    """Resolves an item string to a ProductFamily, and a specific Product if
    the customer (or the model) named an exact SKU."""
    stripped = item_text.strip()
    for product in kb.products:
        if stripped.upper() == product.sku.upper():
            return _family_for_sku(settings_obj, product.sku), product

    normalized_item = normalize(item_text)
    item_words = _alias_word_set(normalized_item)
    lexicon = _load_lexicon_products(settings_obj.paths.lexicon)

    # Alias matching is on WORD SETS, order-insensitive: an alias matches
    # if every one of its words appears somewhere in the item text. The
    # "best" match is the alias with the most words (most specific), not
    # the most characters -- a short, specific alias like "gift box large"
    # must be able to beat a longer but generic one shared by multiple
    # SKUs, like "diwali gift box".
    best_word_count = 0
    best_skus: set[str] = set()
    for sku, aliases in lexicon.items():
        for alias in aliases:
            alias_words = _alias_word_set(alias)
            if not alias_words or not alias_words <= item_words:
                continue
            count = len(alias_words)
            if count > best_word_count:
                best_word_count = count
                best_skus = {sku}
            elif count == best_word_count:
                best_skus.add(sku)

    if not best_skus:
        raise PricingError("NOT_ON_MENU", f"'{item_text}' is not on our menu.")

    matched_families: dict[str, ProductFamily] = {}
    for sku in best_skus:
        family = _family_for_sku(settings_obj, sku)
        matched_families[family.name] = family

    if len(matched_families) > 1:
        matched_families = _disambiguate_by_size(
            matched_families, item_words, lexicon, settings_obj
        ) or matched_families

    if len(matched_families) > 1:
        options = []
        for family in matched_families.values():
            for product in family.products:
                options.append(f"{product.item} ({product.pack}, Rs {product.price_inr})")
        raise PricingError(
            "AMBIGUOUS",
            f"'{item_text}' could mean more than one thing: {'; '.join(options)}. "
            "Please say which one you mean.",
            suggestions=options,
        )

    return next(iter(matched_families.values())), None


def _disambiguate_by_size(
    matched_families: dict[str, ProductFamily],
    item_words: frozenset[str],
    lexicon: dict[str, list[str]],
    settings_obj: Settings,
) -> dict[str, ProductFamily] | None:
    """If the item text contains a size word (large/small/bada/chhota/...)
    that uniquely picks out one of several tied families, narrow to it.
    Returns None (no narrowing) if the item text's size is absent or
    ambiguous, or if more than one tied family shares that size."""
    sizes = _load_sizes(settings_obj.paths.lexicon)
    if not sizes:
        return None

    item_sizes = {category for category, words in sizes.items() if words & item_words}
    if len(item_sizes) != 1:
        return None
    target_size = next(iter(item_sizes))

    narrowed: dict[str, ProductFamily] = {}
    for name, family in matched_families.items():
        family_words: set[str] = set()
        for product in family.products:
            for alias in lexicon.get(product.sku, []):
                family_words |= _alias_word_set(alias)
        family_sizes = {category for category, words in sizes.items() if words & family_words}
        if family_sizes == {target_size}:
            narrowed[name] = family

    return narrowed if len(narrowed) == 1 else None


def _normalize_unit_amount(
    unit: str, amount: float, family: ProductFamily, specific_product: Product | None
) -> tuple[float, list[Product]]:
    """Returns (target_amount_in_base_units, candidate_products_for_dp)."""
    unit_key = unit.strip().lower()
    unit_kind = family.unit_kind
    candidates = [specific_product] if specific_product is not None else family.products

    if unit_key in WEIGHT_UNITS:
        if unit_kind != "g":
            raise PricingError(
                "UNIT_MISMATCH",
                f"{family.name} is not sold by weight. Please use the correct unit.",
            )
        return amount * WEIGHT_UNITS[unit_key], candidates

    if unit_key in PIECE_UNITS:
        if unit_kind != "piece":
            raise PricingError(
                "UNIT_MISMATCH",
                f"{family.name} is not sold by the piece. Please use the correct unit.",
            )
        return amount, candidates

    if unit_key in BOX_UNITS:
        if unit_kind != "box":
            raise PricingError(
                "UNIT_MISMATCH",
                f"{family.name} is not sold by the box. Please use the correct unit.",
            )
        return amount, candidates

    if unit_key in PACK_UNITS:
        if specific_product is None and len(family.products) > 1:
            raise PricingError(
                "UNIT_MISMATCH",
                f"{family.name} comes in more than one pack size. Please say how many "
                "kg/g (or which exact size) you want.",
            )
        pack_product = specific_product or family.products[0]
        return amount * pack_product.pack_size, [pack_product]

    raise PricingError("UNIT_MISMATCH", f"Unrecognised unit: '{unit}'.")


@dataclass(frozen=True)
class OrderLine:
    sku: str
    item: str
    pack: str
    packs: int
    unit_price: int
    line_total: int


def _solve_packs(
    target_amount: float, candidates: list[Product], max_order_units: int
) -> list[OrderLine]:
    if not (isinstance(target_amount, (int, float)) and math.isfinite(target_amount)) or target_amount <= 0:
        raise PricingError("INVALID_QUANTITY", "Quantity must be a positive number.")

    target_amount = round(target_amount, 6)
    pack_sizes = [int(round(p.pack_size)) for p in candidates]
    gcd = pack_sizes[0]
    for size in pack_sizes[1:]:
        gcd = math.gcd(gcd, size)

    target_int = int(round(target_amount))
    if abs(target_amount - target_int) > 1e-6 or target_int % gcd != 0:
        suggestion = ", ".join(f"sold in {p.pack} packs, Rs {p.price_inr} each" for p in candidates)
        raise PricingError(
            "PACK_SIZE",
            f"That exact amount isn't available. {suggestion}.",
            suggestions=[suggestion],
        )

    target_units = target_int // gcd
    pack_units = [size // gcd for size in pack_sizes]
    max_reachable_units = max_order_units * max(pack_units)
    if target_units > max_reachable_units:
        raise PricingError(
            "INVALID_QUANTITY",
            f"That quantity is too large for a single order line (max {max_order_units} packs).",
        )

    INF = float("inf")
    dp_cost = [INF] * (target_units + 1)
    dp_choice = [-1] * (target_units + 1)
    dp_cost[0] = 0
    for units in range(1, target_units + 1):
        for idx, pu in enumerate(pack_units):
            if pu <= units and dp_cost[units - pu] + candidates[idx].price_inr < dp_cost[units]:
                dp_cost[units] = dp_cost[units - pu] + candidates[idx].price_inr
                dp_choice[units] = idx

    if dp_cost[target_units] == INF:
        suggestion = ", ".join(f"sold in {p.pack} packs, Rs {p.price_inr} each" for p in candidates)
        raise PricingError(
            "PACK_SIZE",
            f"That exact amount isn't available. {suggestion}.",
            suggestions=[suggestion],
        )

    counts = [0] * len(candidates)
    remaining = target_units
    while remaining > 0:
        idx = dp_choice[remaining]
        counts[idx] += 1
        remaining -= pack_units[idx]

    total_packs = sum(counts)
    if total_packs > max_order_units:
        raise PricingError(
            "INVALID_QUANTITY",
            f"That quantity needs {total_packs} packs, more than the maximum of {max_order_units}.",
        )

    lines = []
    for idx, count in enumerate(counts):
        if count == 0:
            continue
        product = candidates[idx]
        lines.append(
            OrderLine(
                sku=product.sku,
                item=product.item,
                pack=product.pack,
                packs=count,
                unit_price=product.price_inr,
                line_total=count * product.price_inr,
            )
        )
    return lines


@dataclass(frozen=True)
class DeliveryInfo:
    status: str  # "free" | "charged" | "unknown" | "not_available"
    distance_km: float | None
    fee: int | None


@dataclass(frozen=True)
class BulkInfo:
    is_bulk: bool
    reasons: list[str]
    notice_days: int
    advance_amount: int
    notice_too_short: bool


@dataclass(frozen=True)
class OrderQuote:
    lines: list[OrderLine]
    subtotal: int
    giftbox_count: int
    giftbox_subtotal: int
    discount_amount: int
    goods_total: int
    delivery: DeliveryInfo
    grand_total: int
    sweets_kg: float
    bulk: BulkInfo
    cod_allowed: bool
    preorder_closed: bool
    notes: list[str]
    source_ids: list[str]
    allowed_amounts: list[int]

    def to_tool_text(self) -> str:
        parts = []
        for line in self.lines:
            parts.append(f"{line.item} {line.pack} × {line.packs} = ₹{format_inr(line.line_total)}")
        parts.append(f"Subtotal ₹{format_inr(self.subtotal)}")
        if self.discount_amount:
            parts.append(f"Gift box discount -₹{format_inr(self.discount_amount)}")

        d = self.delivery
        if d.status == "unknown":
            parts.append(
                "Delivery: not calculated (distance not given). Rule: free for orders "
                f"≥ ₹{format_inr(round(default_settings.policy.free_delivery_min_inr))} within "
                f"{default_settings.policy.delivery_radius_km} km, otherwise "
                f"₹{format_inr(round(default_settings.policy.delivery_fee_inr))}."
            )
        elif d.status == "not_available":
            parts.append(
                f"Delivery: not available beyond {default_settings.policy.delivery_radius_km} km "
                "— pickup from the shop or book your own courier"
            )
        elif d.status == "free":
            parts.append(
                f"Delivery: FREE ({d.distance_km:g} km, order ≥ "
                f"₹{format_inr(round(default_settings.policy.free_delivery_min_inr))})"
            )
        else:
            parts.append(
                f"Delivery: ₹{format_inr(d.fee)} ({d.distance_km:g} km, order < "
                f"₹{format_inr(round(default_settings.policy.free_delivery_min_inr))})"
            )

        parts.append(f"TOTAL ₹{format_inr(self.grand_total)}")
        parts.append(f"Cash on delivery: {'allowed' if self.cod_allowed else 'not allowed'}")
        if self.bulk.is_bulk:
            parts.append(
                f"Bulk order: yes (notice {self.bulk.notice_days} days, "
                f"advance ₹{format_inr(self.bulk.advance_amount)})"
            )
        else:
            parts.append("Bulk order: no")
        for note in self.notes:
            parts.append(note)
        return " | ".join(parts)


def _parse_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def quote_order(
    items: list[dict],
    distance_km: float | None = None,
    delivery_date: str | date | None = None,
    today: date | None = None,
    *,
    kb: KnowledgeBase | None = None,
    settings_obj: Settings | None = None,
) -> OrderQuote:
    settings_obj = settings_obj or default_settings
    kb = kb or load_knowledge_base(settings_obj)
    policy = settings_obj.policy

    if distance_km is not None and distance_km < 0:
        raise PricingError("INVALID_DISTANCE", "Distance cannot be negative.")

    all_lines: list[OrderLine] = []
    for item_spec in items:
        family, specific_product = _resolve_item(item_spec["item"], kb, settings_obj)
        target_amount, candidates = _normalize_unit_amount(
            item_spec["unit"], item_spec["amount"], family, specific_product
        )
        all_lines.extend(_solve_packs(target_amount, candidates, policy.max_order_units))

    subtotal = sum(line.line_total for line in all_lines)
    giftbox_lines = [line for line in all_lines if line.sku in GIFT_BOX_SKUS]
    giftbox_count = sum(line.packs for line in giftbox_lines)
    giftbox_subtotal = sum(line.line_total for line in giftbox_lines)

    discount_amount = 0
    if giftbox_count >= policy.giftbox_discount_min_boxes:
        discount_amount = round_half_up(giftbox_subtotal * policy.giftbox_discount_pct / 100)

    goods_total = subtotal - discount_amount

    notes: list[str] = []
    if distance_km is None:
        delivery = DeliveryInfo(status="unknown", distance_km=None, fee=None)
        grand_total = goods_total
    elif distance_km > policy.delivery_radius_km:
        delivery = DeliveryInfo(status="not_available", distance_km=distance_km, fee=None)
        grand_total = goods_total
        notes.append("We do not deliver beyond our radius; pickup from the shop or book your own courier.")
    else:
        fee = 0 if goods_total >= policy.free_delivery_min_inr else round(policy.delivery_fee_inr)
        delivery = DeliveryInfo(
            status="free" if fee == 0 else "charged", distance_km=distance_km, fee=fee
        )
        grand_total = goods_total + fee

    sweets_grams = sum(
        line.packs * kb.get_product(line.sku).pack_size
        for line in all_lines
        if kb.get_product(line.sku).type in SWEET_TYPES
    )
    sweets_kg = sweets_grams / 1000

    bulk_reasons = []
    if sweets_kg > policy.bulk_sweets_kg_over:
        bulk_reasons.append("sweets_kg_over_limit")
    if giftbox_count > policy.bulk_giftboxes_over:
        bulk_reasons.append("giftboxes_over_limit")
    is_bulk = bool(bulk_reasons)

    notice_too_short = False
    parsed_date = _parse_date(delivery_date)
    today = today or date.today()
    advance_amount = 0
    notice_days = 0
    if is_bulk:
        notice_days = policy.bulk_notice_days
        advance_amount = round_half_up(grand_total * policy.bulk_advance_pct / 100)
        if parsed_date is not None and (parsed_date - today).days < notice_days:
            notice_too_short = True
            notes.append(f"Bulk orders need {notice_days} days' notice; the requested date is too soon.")

    cod_allowed = grand_total <= policy.cod_max_inr

    preorder_closed = False
    preorder_deadline = _parse_date(policy.giftbox_preorder_until)
    if giftbox_count > 0 and parsed_date is not None and parsed_date > preorder_deadline:
        preorder_closed = True
        notes.append(f"Gift boxes can only be pre-ordered until {preorder_deadline.isoformat()}.")

    source_ids = {line.sku and f"prices.csv#{line.sku}" for line in all_lines}
    source_ids.discard(None)
    source_ids.add("policies.md#delivery")
    source_ids.add("policies.md#payment")
    if is_bulk:
        source_ids.add("policies.md#bulk-orders")
    if giftbox_count > 0 or preorder_closed:
        source_ids.add("policies.md#diwali-2026-gift-boxes-and-discounts")

    amounts = {line.unit_price for line in all_lines} | {line.line_total for line in all_lines}
    amounts.add(subtotal)
    if discount_amount:
        amounts.add(discount_amount)
        amounts.add(giftbox_subtotal)
    amounts.add(goods_total)
    if delivery.fee is not None:
        amounts.add(delivery.fee)
    amounts.add(grand_total)
    if advance_amount:
        amounts.add(advance_amount)

    return OrderQuote(
        lines=all_lines,
        subtotal=subtotal,
        giftbox_count=giftbox_count,
        giftbox_subtotal=giftbox_subtotal,
        discount_amount=discount_amount,
        goods_total=goods_total,
        delivery=delivery,
        grand_total=grand_total,
        sweets_kg=sweets_kg,
        bulk=BulkInfo(
            is_bulk=is_bulk,
            reasons=bulk_reasons,
            notice_days=notice_days,
            advance_amount=advance_amount,
            notice_too_short=notice_too_short,
        ),
        cod_allowed=cod_allowed,
        preorder_closed=preorder_closed,
        notes=notes,
        source_ids=sorted(source_ids),
        allowed_amounts=sorted(amounts),
    )
