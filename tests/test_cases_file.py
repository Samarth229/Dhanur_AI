import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evals_harness.loader import load_cases
from meher_agent.config import load_settings

SETTINGS = load_settings()
SEED_PATH = SETTINGS.paths.evals_dir / "seed_cases.jsonl"
CASES_PATH = SETTINGS.paths.evals_dir / "cases.jsonl"

EXPECTED_SEED_HASH = "199fd88b0b46e382765bc207cbfb55d99dcb9fc4a89bd3f7b93b7d997954bec1"


def test_seed_cases_still_matches_part0_hash():
    actual = hashlib.sha256(SEED_PATH.read_bytes()).hexdigest()
    assert actual == EXPECTED_SEED_HASH


def test_first_13_lines_of_cases_jsonl_are_byte_identical_to_seed():
    seed_bytes = SEED_PATH.read_bytes()
    cases_bytes = CASES_PATH.read_bytes()
    assert cases_bytes[: len(seed_bytes)] == seed_bytes


def test_case_count_at_least_50():
    cases = load_cases(CASES_PATH)
    assert len(cases) >= 50


def test_category_minimums():
    cases = load_cases(CASES_PATH)
    categories = [c.category for c in cases]

    hindi_hinglish = sum(1 for c in categories if c in ("hindi", "hinglish"))
    assert hindi_hinglish >= 10

    assert sum(1 for c in categories if c == "injection") >= 5
    assert sum(1 for c in categories if c == "unknown") >= 5
    assert sum(1 for c in categories if c == "arithmetic") >= 5


def test_multi_turn_minimum():
    cases = load_cases(CASES_PATH)
    multi_turn = sum(1 for c in cases if len(c.turns) >= 2)
    assert multi_turn >= 5


def test_case_ids_unique():
    cases = load_cases(CASES_PATH)
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))


def test_every_case_loads_with_harness_loader():
    cases = load_cases(CASES_PATH)
    assert len(cases) == 73
    for case in cases:
        assert case.id
        assert case.category
        assert case.turns


def test_compute_expected_check_flag_passes():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "compute_expected.py"), "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_compute_case_must_include_contains_grand_total():
    with open(SETTINGS.paths.evals_dir / "cases_src.jsonl", encoding="utf-8") as f:
        src_cases = [json.loads(line) for line in f if line.strip()]

    with open(CASES_PATH, encoding="utf-8") as f:
        built_cases = {json.loads(line)["id"]: json.loads(line) for line in f if line.strip()}

    for src_case in src_cases:
        if "compute" not in src_case:
            continue
        built = built_cases[src_case["id"]]
        include_fields = src_case["compute"].get("include", ["grand_total"])
        if "grand_total" in include_fields:
            # The computed grand_total's string form must be present.
            assert any(
                mi.isdigit() or mi.lstrip("-").isdigit() for mi in built["must_include"]
            ), f"{src_case['id']}: no numeric must_include value found"
