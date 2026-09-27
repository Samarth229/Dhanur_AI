"""Loads eval case files (JSONL). Pure parsing, no HTTP, no service code."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class CaseLoadError(Exception):
    pass


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    turns: list[str]
    must_include: list[str] = field(default_factory=list)
    must_include_any: list[str] = field(default_factory=list)
    must_not_include: list[str] = field(default_factory=list)
    expect_action: str | None = None
    expect_lead: dict[str, Any] = field(default_factory=dict)
    allowed_amounts: list[float] = field(default_factory=list)


_REQUIRED_FIELDS = ("id", "category", "turns")
_OPTIONAL_FIELDS = (
    "must_include",
    "must_include_any",
    "must_not_include",
    "expect_action",
    "expect_lead",
    "allowed_amounts",
)


def load_cases(path: str | Path) -> list[Case]:
    path = Path(path)
    if not path.exists():
        raise CaseLoadError(f"Cases file not found: {path}")

    cases: list[Case] = []
    seen_ids: set[str] = set()

    with open(path, encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CaseLoadError(f"Line {line_no}: invalid JSON ({exc})")

            if not isinstance(data, dict):
                raise CaseLoadError(f"Line {line_no}: each line must be a JSON object")

            missing = [f for f in _REQUIRED_FIELDS if f not in data]
            if missing:
                raise CaseLoadError(f"Line {line_no}: missing required field(s): {', '.join(missing)}")

            case_id = data["id"]
            if not isinstance(case_id, str) or not case_id:
                raise CaseLoadError(f"Line {line_no}: 'id' must be a non-empty string")
            if case_id in seen_ids:
                raise CaseLoadError(f"Line {line_no}: duplicate case id '{case_id}'")
            seen_ids.add(case_id)

            turns = data["turns"]
            if not isinstance(turns, list) or not turns or not all(isinstance(t, str) for t in turns):
                raise CaseLoadError(f"Line {line_no}: 'turns' must be a non-empty list of strings")

            category = data["category"]
            if not isinstance(category, str) or not category:
                raise CaseLoadError(f"Line {line_no}: 'category' must be a non-empty string")

            cases.append(
                Case(
                    id=case_id,
                    category=category,
                    turns=turns,
                    must_include=data.get("must_include", []),
                    must_include_any=data.get("must_include_any", []),
                    must_not_include=data.get("must_not_include", []),
                    expect_action=data.get("expect_action"),
                    expect_lead=data.get("expect_lead", {}),
                    allowed_amounts=data.get("allowed_amounts", []),
                )
            )

    return cases
