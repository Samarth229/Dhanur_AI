import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.config import load_settings
from meher_agent.knowledge import load_knowledge_base, slugify

EXPECTED_SECTION_IDS = {
    "policies.md#prices-and-gst",
    "policies.md#payment",
    "policies.md#delivery",
    "policies.md#bulk-orders",
    "policies.md#diwali-2026-gift-boxes-and-discounts",
    "policies.md#returns-and-damaged-deliveries",
    "policies.md#ingredients-and-allergens",
    "policies.md#storage",
    "policies.md#wedding-and-custom-orders",
    "policies.md#complaints",
    "business.md#about",
    "business.md#address",
    "business.md#opening-hours",
    "business.md#how-to-order",
    "business.md#contact",
    "business.md#languages",
}


def _kb():
    return load_knowledge_base(load_settings())


def test_slugify():
    assert slugify("Bulk orders") == "bulk-orders"
    assert slugify("Diwali 2026 gift boxes and discounts") == "diwali-2026-gift-boxes-and-discounts"
    assert slugify("  Extra   Spaces  ") == "extra-spaces"
    assert slugify("Returns & Damaged Deliveries!") == "returns-damaged-deliveries"


def test_all_14_skus_load_with_correct_price_and_pack():
    kb = _kb()
    assert len(kb.products) == 14

    kk1000 = kb.get_product("KK-1000")
    assert kk1000.price_inr == 1200
    assert kk1000.pack_size == 1000
    assert kk1000.pack_unit == "g"

    sm1 = kb.get_product("SM-1")
    assert sm1.price_inr == 20
    assert sm1.pack_size == 1
    assert sm1.pack_unit == "piece"

    gbl = kb.get_product("GBL")
    assert gbl.price_inr == 1450
    assert gbl.pack_size == 1
    assert gbl.pack_unit == "box"


def test_contains_parsed_correctly():
    kb = _kb()
    gbl = kb.get_product("GBL")
    assert gbl.contains == ["cashew", "almonds", "milk"]

    ml1000 = kb.get_product("ML-1000")
    assert ml1000.contains == []


def test_section_ids_exact_set():
    kb = _kb()
    actual_ids = {s.id for s in kb.sections}
    assert actual_ids == EXPECTED_SECTION_IDS
    assert len(kb.sections) == 16


def test_valid_source_ids_has_30_items():
    kb = _kb()
    assert len(kb.valid_source_ids) == 30


def test_render_full_context_contains_every_source_id():
    kb = _kb()
    context = kb.render_full_context()
    for source_id in kb.valid_source_ids:
        assert source_id in context, f"{source_id} missing from render_full_context()"
