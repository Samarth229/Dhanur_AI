import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.config import load_settings
from meher_agent.knowledge import load_knowledge_base
from meher_agent.pricing import PricingError, format_inr, quote_order

SETTINGS = load_settings()
KB = load_knowledge_base(SETTINGS)


def q(items, **kwargs):
    return quote_order(items, settings_obj=SETTINGS, **kwargs)


def item(name, amount, unit):
    return {"item": name, "amount": amount, "unit": unit}


# ---------------------------------------------------------------------------
# Seed values
# ---------------------------------------------------------------------------


def test_seed_kaju_katli_and_gift_box():
    quote = q([item("kaju katli", 2, "kg"), item("GBL", 1, "box")], distance_km=5)
    assert quote.grand_total == 3850
    assert quote.delivery.status == "free"


def test_seed_motichoor_and_samosa():
    quote = q([item("motichoor laddoo", 3, "kg"), item("samosa", 10, "piece")], distance_km=2)
    assert quote.subtotal == 1880
    assert quote.grand_total == 1880
    assert quote.delivery.status == "free"


def test_seed_60_gbs_bulk_discount():
    quote = q([item("GBS", 60, "box")])
    assert quote.subtotal == 39000
    assert quote.discount_amount == 1950
    assert quote.grand_total == 37050
    assert quote.bulk.is_bulk
    assert quote.bulk.advance_amount == 11115


def test_seed_30_gbl_bulk_no_discount():
    quote = q([item("GBL", 30, "box")])
    assert quote.grand_total == 43500
    assert quote.discount_amount == 0
    assert quote.bulk.is_bulk
    assert quote.bulk.advance_amount == 13050


# ---------------------------------------------------------------------------
# Pack combination DP
# ---------------------------------------------------------------------------


def test_1_5_kg_kaju_katli_combines_packs():
    quote = q([item("kaju katli", 1.5, "kg")])
    assert quote.grand_total == 1820
    skus = {line.sku for line in quote.lines}
    assert skus == {"KK-1000", "KK-500"}


def test_1_kg_kaju_katli_picks_cheaper_single_pack():
    quote = q([item("kaju katli", 1, "kg")])
    assert quote.grand_total == 1200
    assert len(quote.lines) == 1
    assert quote.lines[0].sku == "KK-1000"


def test_pack_unit_devanagari_alias():
    # Fix 7: "पैक" must mean one pack (500 g), not kilograms.
    quote = q([item("rasmalai", 2, "पैक")])
    assert quote.grand_total == 680


def test_pack_unit_dabba_alias():
    quote = q([item("rasmalai", 2, "dabba")])
    assert quote.grand_total == 680


def test_pack_vs_kg_give_different_totals():
    pack_quote = q([item("rasmalai", 2, "pack")])
    kg_quote = q([item("rasmalai", 2, "kg")])
    assert pack_quote.grand_total != kg_quote.grand_total


def test_750g_motichoor_pack_size_error():
    with pytest.raises(PricingError) as exc_info:
        q([item("motichoor laddoo", 750, "g")])
    assert exc_info.value.code == "PACK_SIZE"


def test_rabri_not_on_menu():
    with pytest.raises(PricingError) as exc_info:
        q([item("rabri", 1, "kg")])
    assert exc_info.value.code == "NOT_ON_MENU"


def test_laddoo_ambiguous():
    with pytest.raises(PricingError) as exc_info:
        q([item("laddoo", 1, "kg")])
    assert exc_info.value.code == "AMBIGUOUS"


def test_gift_box_ambiguous():
    with pytest.raises(PricingError) as exc_info:
        q([item("gift box", 1, "box")])
    assert exc_info.value.code == "AMBIGUOUS"


# ---------------------------------------------------------------------------
# Size-word disambiguation (arith-01 regression fix)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase,expected_sku",
    [
        ("large Diwali gift box", "GBL"),
        ("diwali box large", "GBL"),
        ("bada gift box", "GBL"),
        ("छोटा गिफ्ट बॉक्स", "GBS"),  # chhota gift box
        ("small gift box", "GBS"),
    ],
)
def test_size_word_disambiguates_gift_box(phrase, expected_sku):
    quote = q([item(phrase, 1, "box")])
    assert quote.lines[0].sku == expected_sku


def test_plain_gift_box_still_ambiguous_without_size_word():
    with pytest.raises(PricingError) as exc_info:
        q([item("diwali gift box", 1, "box")])
    assert exc_info.value.code == "AMBIGUOUS"


def test_sugar_free_kaju_katli_resolves_correctly():
    quote = q([item("sugar free kaju katli", 500, "g")])
    assert quote.grand_total == 780
    assert quote.lines[0].sku == "KKSF-500"


# ---------------------------------------------------------------------------
# Multilingual name resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,amount,unit,expected_sku",
    [
        ("motichoor ladoo", 1, "kg", "ML-1000"),
        ("samose", 5, "piece", "SM-1"),
        ("काजू कतली", 1, "kg", "KK-1000"),
    ],
)
def test_multilingual_name_resolution(name, amount, unit, expected_sku):
    quote = q([item(name, amount, unit)])
    assert quote.lines[0].sku == expected_sku


# ---------------------------------------------------------------------------
# Unit and quantity validation
# ---------------------------------------------------------------------------


def test_samosa_with_kg_unit_mismatch():
    with pytest.raises(PricingError) as exc_info:
        q([item("samosa", 1, "kg")])
    assert exc_info.value.code == "UNIT_MISMATCH"


@pytest.mark.parametrize("amount", [0, -2])
def test_invalid_quantity(amount):
    with pytest.raises(PricingError) as exc_info:
        q([item("samosa", amount, "piece")])
    assert exc_info.value.code == "INVALID_QUANTITY"


def test_invalid_distance():
    with pytest.raises(PricingError) as exc_info:
        q([item("samosa", 5, "piece")], distance_km=-1)
    assert exc_info.value.code == "INVALID_DISTANCE"


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_delivery_fee_boundary_below_and_at_free_threshold():
    assert SETTINGS.policy.free_delivery_min_inr == 999

    # Rasmalai (Rs 340) + Diwali Gift Box Small (Rs 650) = Rs 990, just below Rs 999.
    quote_below = q([item("rasmalai", 500, "g"), item("GBS", 1, "box")], distance_km=1)
    assert quote_below.goods_total == 990
    assert quote_below.delivery.fee == 60

    # Gulab Jamun (Rs 480) + Besan Laddoo (Rs 520) = Rs 1000, at/above Rs 999.
    quote_at = q([item("gulab jamun", 1, "kg"), item("besan laddoo", 1, "kg")], distance_km=1)
    assert quote_at.goods_total == 1000
    assert quote_at.delivery.fee == 0


def test_delivery_distance_boundary():
    quote_at_radius = q([item("samosa", 1, "piece")], distance_km=8)
    assert quote_at_radius.delivery.status in {"free", "charged"}

    quote_beyond = q([item("samosa", 1, "piece")], distance_km=8.1)
    assert quote_beyond.delivery.status == "not_available"
    assert quote_beyond.delivery.fee is None


def test_giftbox_bulk_boundary():
    quote_25 = q([item("GBS", 25, "box")])
    assert not quote_25.bulk.is_bulk

    quote_26 = q([item("GBS", 26, "box")])
    assert quote_26.bulk.is_bulk


def test_giftbox_discount_boundary():
    quote_49 = q([item("GBS", 49, "box")])
    assert quote_49.discount_amount == 0

    quote_50 = q([item("GBS", 50, "box")])
    assert quote_50.discount_amount == 1625


def test_discount_applies_across_both_giftbox_types():
    quote = q([item("GBS", 25, "box"), item("GBL", 25, "box")])
    assert quote.giftbox_count == 50
    assert quote.discount_amount == 2625


def test_bulk_sweets_kg_boundary():
    quote_10 = q([item("kaju katli", 10, "kg")])
    assert not quote_10.bulk.is_bulk

    quote_10_5 = q([item("kaju katli", 10.5, "kg")])
    assert quote_10_5.bulk.is_bulk


def test_namkeen_does_not_count_toward_bulk():
    quote = q([item("kaju katli", 6, "kg"), item("aloo bhujia", 5, "pack")])
    assert not quote.bulk.is_bulk


def test_cod_boundary():
    # 250 samosas @ Rs 20 = exactly Rs 5000.
    quote_at_5000 = q([item("samosa", 250, "piece")])
    assert quote_at_5000.grand_total == 5000
    assert quote_at_5000.cod_allowed is True

    # 251 samosas = Rs 5020, over the Rs 5000 cap.
    quote_over_5000 = q([item("samosa", 251, "piece")])
    assert quote_over_5000.grand_total == 5020
    assert quote_over_5000.cod_allowed is False


def test_cod_allowed_flag_directly():
    quote_low = q([item("kaju katli", 1, "kg")])  # 1200
    assert quote_low.cod_allowed is True


# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------


def test_rounding_51_gbs():
    quote = q([item("GBS", 51, "box")])
    assert quote.discount_amount == 1658
    assert quote.grand_total == 31492


# ---------------------------------------------------------------------------
# Delivery unknown / date flags
# ---------------------------------------------------------------------------


def test_no_distance_status_unknown_and_no_extra_amount():
    quote = q([item("kaju katli", 1, "kg")])
    assert quote.delivery.status == "unknown"
    assert quote.grand_total == quote.goods_total
    assert quote.delivery.fee is None


def test_preorder_closed_flag():
    quote = q([item("GBS", 1, "box")], delivery_date="2026-11-10")
    assert quote.preorder_closed


def test_notice_too_short_flag():
    today = date(2026, 1, 1)
    quote = q(
        [item("GBS", 60, "box")],
        delivery_date="2026-01-02",
        today=today,
    )
    assert quote.bulk.notice_too_short


# ---------------------------------------------------------------------------
# Source IDs
# ---------------------------------------------------------------------------


def test_source_ids_subset_of_valid_ids():
    quote = q([item("kaju katli", 2, "kg"), item("GBL", 1, "box")], distance_km=5)
    assert set(quote.source_ids) <= KB.valid_source_ids


# ---------------------------------------------------------------------------
# format_inr
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "n,expected",
    [
        (3850, "3,850"),
        (37050, "37,050"),
        (100000, "1,00,000"),
        (12345678, "1,23,45,678"),
    ],
)
def test_format_inr(n, expected):
    assert format_inr(n) == expected


# ---------------------------------------------------------------------------
# Config-vs-policy-text consistency
# ---------------------------------------------------------------------------


def test_config_values_match_policy_text():
    policy_text = (SETTINGS.paths.data_dir / "policies.md").read_text(encoding="utf-8")
    assert "8 km" in policy_text
    assert "999" in policy_text
    assert "60" in policy_text
    assert "5,000" in policy_text
    assert "5%" in policy_text
    assert "30%" in policy_text
    assert "3 days" in policy_text
    assert "10 kg" in policy_text
    assert "25 gift boxes" in policy_text
    assert "5 November 2026" in policy_text
