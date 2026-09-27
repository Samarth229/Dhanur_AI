import dataclasses
import json
import sys
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evals_harness.loader import CaseLoadError, load_cases
from evals_harness.runner import run_eval
from meher_agent.config import load_settings

SETTINGS = load_settings()


def settings_with_reports_dir(reports_dir: Path):
    """Runner tests must never write into the project's real reports/ dir."""
    return dataclasses.replace(SETTINGS, paths=dataclasses.replace(SETTINGS.paths, reports_dir=reports_dir))


def _chat_body(reply="Hi there.", actions=None):
    return {
        "reply": reply,
        "sources": [],
        "actions": actions or [],
        "handoff": False,
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "model_calls": 1, "latency_ms": 50, "estimated": False},
    }


def make_handler():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "model": "test-model"})
        if request.url.path == "/chat":
            payload = json.loads(request.content)
            if payload["message"] == "TRIGGER_TIMEOUT":
                raise httpx.TimeoutException("simulated timeout")
            return httpx.Response(200, json=_chat_body(reply=f"Reply to: {payload['message']}"))
        return httpx.Response(404)

    return handler


def write_cases_file(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Loader errors
# ---------------------------------------------------------------------------


def test_load_cases_malformed_json_line(tmp_path):
    path = write_cases_file(tmp_path, ['{"id": "c1", "category": "fact", "turns": ["hi"]}', "not json at all"])
    with pytest.raises(CaseLoadError) as exc_info:
        load_cases(path)
    assert "Line 2" in str(exc_info.value)


def test_load_cases_duplicate_id(tmp_path):
    path = write_cases_file(
        tmp_path,
        [
            '{"id": "c1", "category": "fact", "turns": ["hi"]}',
            '{"id": "c1", "category": "price", "turns": ["hello"]}',
        ],
    )
    with pytest.raises(CaseLoadError) as exc_info:
        load_cases(path)
    assert "duplicate" in str(exc_info.value).lower()
    assert "Line 2" in str(exc_info.value)


def test_load_cases_missing_required_field(tmp_path):
    path = write_cases_file(tmp_path, ['{"id": "c1", "turns": ["hi"]}'])
    with pytest.raises(CaseLoadError) as exc_info:
        load_cases(path)
    assert "category" in str(exc_info.value)


def test_load_cases_skips_blank_lines(tmp_path):
    path = write_cases_file(
        tmp_path, ['{"id": "c1", "category": "fact", "turns": ["hi"]}', "", "   "]
    )
    cases = load_cases(path)
    assert len(cases) == 1


def test_load_cases_missing_file():
    with pytest.raises(CaseLoadError):
        load_cases("does_not_exist.jsonl")


# ---------------------------------------------------------------------------
# Runner: timeout on one case doesn't stop the whole eval
# ---------------------------------------------------------------------------


def test_timeout_marks_case_error_and_continues(tmp_path):
    cases_path = write_cases_file(
        tmp_path,
        [
            json.dumps({"id": "timeout-case", "category": "fact", "turns": ["hello", "TRIGGER_TIMEOUT"]}),
            json.dumps({"id": "normal-case", "category": "fact", "turns": ["hello"]}),
        ],
    )
    transport = httpx.MockTransport(make_handler())
    test_settings = settings_with_reports_dir(tmp_path / "reports")

    exit_code = run_eval(str(cases_path), test_settings, runs=1, base_url="http://testserver", transport=transport)
    assert exit_code == 0

    report = json.loads((test_settings.paths.reports_dir / "eval_report.json").read_text(encoding="utf-8"))
    run0 = report["runs"][0]
    timeout_result = next(r for r in run0 if r["case_id"] == "timeout-case")
    normal_result = next(r for r in run0 if r["case_id"] == "normal-case")

    assert timeout_result["error"] is True
    assert timeout_result["passed"] is False
    assert normal_result["error"] is False


def test_health_check_failure_exits_nonzero(tmp_path):
    cases_path = write_cases_file(
        tmp_path, [json.dumps({"id": "c1", "category": "fact", "turns": ["hi"]})]
    )

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(failing_handler)
    test_settings = settings_with_reports_dir(tmp_path / "reports")
    exit_code = run_eval(str(cases_path), test_settings, runs=1, base_url="http://testserver", transport=transport)
    assert exit_code != 0
