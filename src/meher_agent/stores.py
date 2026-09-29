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
        self._leads: dict[str, list[Lead]] = {}

    def upsert(self, conversation_id: str, fields: dict[str, Any]) -> tuple[Lead, bool]:
        """Returns (lead, created).

        A conversation can produce more than one lead (e.g. two different
        people giving their own contact details in the same chat), so a new
        save_lead call only merges into an existing lead when the name
        matches (casefold) or the call gives no name at all -- a name that
        does not match anything on file starts a new lead instead of
        overwriting someone else's.
        """
        with self._lock:
            existing_leads = self._leads.setdefault(conversation_id, [])
            new_name = fields.get("name")

            match = None
            if not new_name:
                match = existing_leads[-1] if existing_leads else None
            else:
                new_name_cf = str(new_name).casefold()
                for lead in existing_leads:
                    if lead.name and lead.name.casefold() == new_name_cf:
                        match = lead
                        break

            if match is None:
                lead = Lead(conversation_id=conversation_id, **fields)
                existing_leads.append(lead)
                return lead, True

            for key, value in fields.items():
                if value is not None and value != "":
                    setattr(match, key, value)
            match.updated_at = _now_iso()
            return match, False

    def get(self, conversation_id: str) -> Lead | None:
        with self._lock:
            leads = self._leads.get(conversation_id)
            return leads[-1] if leads else None

    def list_masked(self) -> list[dict[str, Any]]:
        with self._lock:
            leads = [lead for leads in self._leads.values() for lead in leads]
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
