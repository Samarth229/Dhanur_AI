"""Guards the starter data files against accidental modification.

These hashes were computed from the untouched files at project setup
time. If any of them change, this test fails on purpose.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.config import load_settings

EXPECTED_HASHES = {
    "prices.csv": "4fde4549ed6a0677c3602c95f152d3df1f3d8f7efdda86d5b73a41e3fc55cee2",
    "policies.md": "31165a24e038118d6052ebf2235dfdfc56f90c00458a7d6c6ff29f59a5b77dfe",
    "business.md": "4b8bb8516cdbdb3f7b1f2cf8cb75b07a779e1246e4a0c36a90345ca3de7ad863",
}

EXPECTED_EVALS_HASH = "199fd88b0b46e382765bc207cbfb55d99dcb9fc4a89bd3f7b93b7d997954bec1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_data_files_unmodified():
    settings = load_settings()
    for filename, expected in EXPECTED_HASHES.items():
        actual = _sha256(settings.paths.data_dir / filename)
        assert actual == expected, f"{filename} has been modified since project setup"


def test_seed_cases_unmodified():
    settings = load_settings()
    actual = _sha256(settings.paths.evals_dir / "seed_cases.jsonl")
    assert actual == EXPECTED_EVALS_HASH, "seed_cases.jsonl has been modified since project setup"
