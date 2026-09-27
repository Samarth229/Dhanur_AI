import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.config import load_settings
from meher_agent.logging_setup import setup_logging
from meher_agent.privacy import MaskingFilter, mask_email, mask_phone, mask_text


def test_mask_email_exact_pdf_example():
    assert mask_email("ritu.m@example.com") == "r*****@example.com"


def test_mask_phone_exact_pdf_example():
    assert mask_phone("9876543210") == "******3210"


def test_mask_text_masks_email_and_phone_in_sentence():
    text = "Contact Ritu at ritu.m@example.com or +91 98765-43210 for the 37050 rupee order."
    masked = mask_text(text)
    assert "ritu.m@example.com" not in masked
    assert "98765" not in masked
    assert "43210" not in masked
    assert "r*****@example.com" in masked
    assert "******3210" in masked
    assert "37050" in masked


def test_mask_text_does_not_touch_prices():
    text = "Total is 37050, or 100000, or 1,00,000, or ₹3,850."
    masked = mask_text(text)
    assert masked == text


def test_mask_text_handles_098_format():
    masked = mask_text("Call 098765 43210 now.")
    assert "98765" not in masked
    assert "43210" not in masked
    assert "******3210" in masked


def test_logging_filter_masks_records(caplog):
    settings_obj = load_settings()
    logger = logging.getLogger("test_privacy_logger")
    logger.setLevel(logging.INFO)
    logger.addFilter(MaskingFilter())

    with caplog.at_level(logging.INFO, logger="test_privacy_logger"):
        logger.info("Customer phone +91 98765-43210 email ritu.m@example.com")

    output = caplog.text
    assert "98765-43210" not in output
    assert "ritu.m@example.com" not in output
    assert "******3210" in output
    assert "r*****@example.com" in output


def test_setup_logging_attaches_masking_filter_to_handler():
    settings_obj = load_settings()
    root = logging.getLogger()
    root.handlers.clear()
    setup_logging(settings_obj)
    assert any(isinstance(f, MaskingFilter) for h in root.handlers for f in h.filters)
