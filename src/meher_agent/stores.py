"""In-memory stores for customer leads and escalations.

Thread-safe (a single lock per store) since the API in later parts may
serve concurrent requests.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from meher_agent.privacy import mask_email, mask_phone


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Lead:
    conversation_id: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    need: str | None = None
    quantity: str | None = None
    date: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class LeadStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._leads: dict[str, Lead] = {}

    def upsert(self, conversation_id: str, fields: dict[str, Any]) -> tuple[Lead, bool]:
        """Returns (lead, created). Merges non-empty fields into any existing lead."""
        with self._lock:
            existing = self._leads.get(conversation_id)
            if existing is None:
                lead = Lead(conversation_id=conversation_id, **fields)
                self._leads[conversation_id] = lead
                return lead, True

            for key, value in fields.items():
                if value is not None and value != "":
                    setattr(existing, key, value)
            existing.updated_at = _now_iso()
            return existing, False

    def get(self, conversation_id: str) -> Lead | None:
        with self._lock:
            return self._leads.get(conversation_id)

    def list_masked(self) -> list[dict[str, Any]]:
        with self._lock:
            leads = list(self._leads.values())
        return [
            {
                "name": lead.name,
                "email": mask_email(lead.email) if lead.email else None,
                "phone": mask_phone(lead.phone) if lead.phone else None,
                "need": lead.need,
                "quantity": lead.quantity,
                "date": lead.date,
                "conversation_id": lead.conversation_id,
                "created_at": lead.created_at,
            }
            for lead in leads
        ]


@dataclass
class Escalation:
    conversation_id: str
    reason: str
    created_at: str = field(default_factory=_now_iso)


class EscalationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._escalations: list[Escalation] = []

    def add(self, conversation_id: str, reason: str) -> Escalation:
        escalation = Escalation(conversation_id=conversation_id, reason=reason)
        with self._lock:
            self._escalations.append(escalation)
        return escalation

    def list(self) -> list[Escalation]:
        with self._lock:
            return list(self._escalations)
