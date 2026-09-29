import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.stores import EscalationStore, LeadStore


def test_upsert_creates_new_lead():
    store = LeadStore()
    lead, created = store.upsert("conv-1", {"name": "Amit", "email": "amit@example.com"})
    assert created is True
    assert lead.name == "Amit"
    assert lead.email == "amit@example.com"


def test_upsert_merges_into_existing_lead_same_conversation():
    store = LeadStore()
    store.upsert("conv-1", {"name": "Amit", "email": "amit@example.com"})
    lead, created = store.upsert("conv-1", {"phone": "9876543210"})
    assert created is False
    assert lead.name == "Amit"
    assert lead.email == "amit@example.com"
    assert lead.phone == "9876543210"


def test_upsert_different_conversation_creates_separate_lead():
    store = LeadStore()
    store.upsert("conv-1", {"name": "Amit", "email": "amit@example.com"})
    store.upsert("conv-2", {"name": "Ritu", "phone": "9876543210"})
    masked = store.list_masked()
    assert len(masked) == 2


def test_list_masked_exact_masking():
    store = LeadStore()
    store.upsert(
        "conv-1",
        {"name": "Ritu Malhotra", "email": "ritu.m@example.com", "phone": "9876543210", "need": "gift boxes"},
    )
    masked = store.list_masked()
    assert len(masked) == 1
    entry = masked[0]
    assert entry["email"] == "r*****@example.com"
    assert entry["phone"] == "******3210"
    assert "ritu.m@example.com" not in str(masked)
    assert "9876543210" not in str(masked)
    assert entry["name"] == "Ritu Malhotra"
    assert entry["need"] == "gift boxes"
    assert entry["conversation_id"] == "conv-1"
    assert "created_at" in entry


def test_upsert_different_names_same_conversation_creates_two_leads():
    # Hotfix (turns 15/16 of the manual chat-page transcript): two different
    # people giving their own contact details in the same chat must produce
    # two separate leads, not merge into one.
    store = LeadStore()
    lead1, created1 = store.upsert("conv-1", {"name": "Ritu Malhotra", "email": "ritu@example.com"})
    lead2, created2 = store.upsert("conv-1", {"name": "Amit Verma", "phone": "9876543210"})
    assert created1 is True
    assert created2 is True
    assert lead1 is not lead2
    masked = store.list_masked()
    assert len(masked) == 2
    names = {m["name"] for m in masked}
    assert names == {"Ritu Malhotra", "Amit Verma"}


def test_upsert_same_name_twice_merges_into_one_lead():
    store = LeadStore()
    store.upsert("conv-1", {"name": "Amit Verma", "email": "amit@example.com"})
    lead, created = store.upsert("conv-1", {"name": "amit verma", "phone": "9876543210"})
    assert created is False
    assert lead.email == "amit@example.com"
    assert lead.phone == "9876543210"
    assert len(store.list_masked()) == 1


def test_list_masked_null_for_missing_contact_fields():
    store = LeadStore()
    store.upsert("conv-1", {"name": "Amit", "email": "amit@example.com"})
    entry = store.list_masked()[0]
    assert entry["phone"] is None


def test_escalation_store_records_and_lists():
    store = EscalationStore()
    store.add("conv-1", "Damaged delivery")
    escalations = store.list()
    assert len(escalations) == 1
    assert escalations[0].conversation_id == "conv-1"
    assert escalations[0].reason == "Damaged delivery"
    assert escalations[0].created_at.endswith("Z")
