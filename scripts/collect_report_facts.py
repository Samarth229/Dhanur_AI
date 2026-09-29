"""Collects real, sourced facts from the repo/reports/logs into
reports/report_data_pack.md (+ .json with the same data), for a human to
write the technical report from. Every number is read from a file or
computed by a command in this script -- nothing here is invented, rounded
creatively, or interpreted. Re-running this script (without changing the
repo) reproduces the same output.

Does not modify any code, cases or config.

Usage:
    python scripts/collect_report_facts.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from meher_agent.config import load_settings  # noqa: E402
from meher_agent.knowledge import load_knowledge_base  # noqa: E402

REPORTS_DIR = ROOT / "reports"
RUNS_DIR = REPORTS_DIR / "runs"
OUT_MD = REPORTS_DIR / "report_data_pack.md"
OUT_JSON = REPORTS_DIR / "report_data_pack.json"

SETTINGS = load_settings()
KB = load_knowledge_base(SETTINGS)

data: dict[str, Any] = {}


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return result.stdout.strip()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(_read(path))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in _read(path).splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# Step 0: privacy check (evidence only, decision already made in the prior
# conversation turn -- restated here from the same source file so the data
# pack is self-contained and reproducible from reports/eval_report.json).
# ---------------------------------------------------------------------------

def collect_privacy_check() -> dict[str, Any]:
    report = _read_json(REPORTS_DIR / "eval_report.json")
    phone_re = re.compile(r"\+?91[\s-]?\d{5}[\s-]?\d{5}|\b\d{10}\b")
    failing_runs = []
    leak_found = False
    for run_idx, run in enumerate(report["runs"], start=1):
        for r in run:
            if r["category"] != "privacy" or r["passed"]:
                continue
            last_reply = r["turns"][-1]["response"]["reply"]
            leaked = bool(phone_re.search(last_reply)) or "+91" in last_reply
            leak_found = leak_found or leaked
            failing_runs.append(
                {
                    "run": run_idx,
                    "case_id": r["case_id"],
                    "reply": last_reply,
                    "failed_checks": [c["name"] + ": " + c.get("details", "") for c in r["checks"] if not c["passed"]],
                    "contains_phone_or_+91": leaked,
                }
            )
    return {
        "source": "reports/eval_report.json (submission run)",
        "leak_found": leak_found,
        "verdict": "SAFETY BUG -- phone/+91 leaked" if leak_found else "wording only, no phone/+91 in any reply",
        "failing_runs": failing_runs,
    }


# ---------------------------------------------------------------------------
# A. Project stats
# ---------------------------------------------------------------------------

def collect_project_stats() -> dict[str, Any]:
    def loc(pattern: str) -> dict[str, int]:
        result = {}
        for path in sorted(ROOT.glob(pattern)):
            result[str(path.relative_to(ROOT)).replace("\\", "/")] = len(_read(path).splitlines())
        return result

    src_loc = loc("src/meher_agent/*.py")
    harness_loc = loc("evals_harness/*.py")
    scripts_loc = loc("scripts/*.py")

    collect_out = _run([sys.executable, "-m", "pytest", "--collect-only", "-q"])
    total_tests_match = re.search(r"(\d+) tests? collected", collect_out)
    total_tests = int(total_tests_match.group(1)) if total_tests_match else None

    per_file_counts = {}
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        count = len(re.findall(r"^def test_", _read(path), re.MULTILINE))
        per_file_counts[str(path.relative_to(ROOT)).replace("\\", "/")] = count

    commit_count = int(_run(["git", "log", "--oneline"]).count("\n")) + (
        1 if _run(["git", "log", "--oneline"]) else 0
    )
    first_commit_date = _run(["git", "log", "--format=%ai", "--reverse"]).splitlines()[0]
    last_commit_date = _run(["git", "log", "-1", "--format=%ai"])

    requirements = []
    for line in _read(ROOT / "requirements.txt").splitlines():
        line = line.strip()
        if line:
            requirements.append(line)

    return {
        "loc_per_module": {"src/meher_agent": src_loc, "evals_harness": harness_loc, "scripts": scripts_loc},
        "loc_totals": {
            "src/meher_agent": sum(src_loc.values()),
            "evals_harness": sum(harness_loc.values()),
            "scripts": sum(scripts_loc.values()),
            "grand_total": sum(src_loc.values()) + sum(harness_loc.values()) + sum(scripts_loc.values()),
        },
        "test_count_total": total_tests,
        "test_count_per_file": per_file_counts,
        "test_count_per_file_sum": sum(per_file_counts.values()),
        "commit_count": commit_count,
        "first_commit_date": first_commit_date,
        "last_commit_date": last_commit_date,
        "requirements_txt": requirements,
        "python_version": sys.version.split()[0],
        "source": "wc-equivalent line counts of src/meher_agent/*.py, evals_harness/*.py, scripts/*.py; "
        "`pytest --collect-only -q`; `git log`; requirements.txt; sys.version",
    }


# ---------------------------------------------------------------------------
# B. Data & lexicon
# ---------------------------------------------------------------------------

def collect_data_and_lexicon() -> dict[str, Any]:
    lexicon_raw = tomllib.loads(_read(Path(SETTINGS.paths.lexicon)))

    policy_sections = [s.id for s in KB.sections if s.file == "policies.md"]
    business_sections = [s.id for s in KB.sections if s.file == "business.md"]

    products_alias_count = {sku: len(aliases) for sku, aliases in lexicon_raw.get("products", {}).items()}
    section_alias_count = {sid: len(aliases) for sid, aliases in lexicon_raw.get("sections", {}).items()}
    intents_sizes = {name: len(words) for name, words in lexicon_raw.get("intents", {}).items()}

    return {
        "sku_count": len(KB.products),
        "policy_section_count": len(policy_sections),
        "policy_section_ids": policy_sections,
        "business_section_count": len(business_sections),
        "business_section_ids": business_sections,
        "valid_source_id_count": len(KB.valid_source_ids),
        "lexicon_product_alias_counts_per_sku": products_alias_count,
        "lexicon_product_alias_total": sum(products_alias_count.values()),
        "lexicon_section_alias_counts": section_alias_count,
        "lexicon_hinglish_marker_count": len(lexicon_raw.get("language", {}).get("hinglish_markers", [])),
        "lexicon_english_function_word_count": len(lexicon_raw.get("language", {}).get("english_function_words", [])),
        "lexicon_intents_sizes": intents_sizes,
        "lexicon_sizes_categories": {k: len(v) for k, v in lexicon_raw.get("sizes", {}).items()},
        "source": "data/prices.csv, data/policies.md, data/business.md (via meher_agent.knowledge), "
        "src/meher_agent/resources/lexicon.toml",
    }


# ---------------------------------------------------------------------------
# C. Config values
# ---------------------------------------------------------------------------

def collect_config_values() -> dict[str, Any]:
    s = SETTINGS
    return {
        "llm": {
            "temperature": s.llm.temperature,
            "max_model_calls": s.llm.max_model_calls,
            "request_timeout_s": s.llm.request_timeout_s,
            "max_tokens": s.llm.max_tokens,
        },
        "agent": {
            "history_messages": s.agent.history_messages,
            "max_sources": s.agent.max_sources,
            "allowed_percentages": list(s.agent.allowed_percentages),
            "today_override": s.agent.today_override,
        },
        "reply": {"max_chars": s.reply.max_chars},
        "retrieval": {
            "mode": s.retrieval.mode,
            "top_k": s.retrieval.top_k,
            "min_score": s.retrieval.min_score,
            "history_weight": s.retrieval.history_weight,
        },
        "policy": {
            "delivery_radius_km": s.policy.delivery_radius_km,
            "free_delivery_min_inr": s.policy.free_delivery_min_inr,
            "delivery_fee_inr": s.policy.delivery_fee_inr,
            "cod_max_inr": s.policy.cod_max_inr,
            "giftbox_discount_min_boxes": s.policy.giftbox_discount_min_boxes,
            "giftbox_discount_pct": s.policy.giftbox_discount_pct,
            "bulk_sweets_kg_over": s.policy.bulk_sweets_kg_over,
            "bulk_giftboxes_over": s.policy.bulk_giftboxes_over,
            "bulk_notice_days": s.policy.bulk_notice_days,
            "bulk_advance_pct": s.policy.bulk_advance_pct,
            "giftbox_preorder_until": s.policy.giftbox_preorder_until,
            "max_order_units": s.policy.max_order_units,
        },
        "eval": {
            "runs": s.eval.runs,
            "request_timeout_s": s.eval.request_timeout_s,
            "concurrency": s.eval.concurrency,
            "base_url": s.eval.base_url,
            "inr_per_usd": s.eval.inr_per_usd,
        },
        "source": "config.toml (via meher_agent.config.load_settings)",
    }


# ---------------------------------------------------------------------------
# D. Case set
# ---------------------------------------------------------------------------

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def collect_case_set() -> dict[str, Any]:
    cases = _read_jsonl(ROOT / "evals" / "cases.jsonl")
    cases_src = _read_jsonl(ROOT / "evals" / "cases_src.jsonl")
    src_by_id = {c["id"]: c for c in cases_src}

    per_category = Counter(c["category"] for c in cases)
    multi_turn = [c for c in cases if len(c["turns"]) > 1]
    max_turns = max(len(c["turns"]) for c in cases)

    devanagari_cases = [c["id"] for c in cases if any(_DEVANAGARI_RE.search(t) for t in c["turns"])]
    hinglish_cases = [c["id"] for c in cases if c["category"] == "hinglish"]
    compute_cases = [c["id"] for c in cases_src if "compute" in c]

    check_usage = {
        "must_include": sum(1 for c in cases if c.get("must_include")),
        "must_include_any": sum(1 for c in cases if c.get("must_include_any")),
        "must_not_include": sum(1 for c in cases if c.get("must_not_include")),
        "allowed_amounts": sum(1 for c in cases if c.get("allowed_amounts")),
    }
    expect_action_values = Counter(c["expect_action"] for c in cases if c.get("expect_action") is not None)
    expect_lead_count = sum(1 for c in cases if c.get("expect_lead"))

    # Cases added after the baseline-full run (73 cases): diff current
    # cases.jsonl ids against that run's own recorded case-id list.
    baseline_run = RUNS_DIR / "20260927-175002-baseline-full" / "eval_report.json"
    baseline_ids: set[str] = set()
    if baseline_run.exists():
        baseline_report = _read_json(baseline_run)
        baseline_ids = {r["case_id"] for r in baseline_report["runs"][0]}
    new_ids = [c["id"] for c in cases if c["id"] not in baseline_ids]
    new_cases_with_notes = [
        {"id": cid, "note": src_by_id.get(cid, {}).get("note", "N/A (not in cases_src.jsonl)")} for cid in new_ids
    ]

    return {
        "total_cases": len(cases),
        "per_category": dict(sorted(per_category.items())),
        "multi_turn_case_count": len(multi_turn),
        "multi_turn_case_ids": [c["id"] for c in multi_turn],
        "max_turns": max_turns,
        "devanagari_case_count": len(devanagari_cases),
        "devanagari_case_ids": devanagari_cases,
        "hinglish_case_count": len(hinglish_cases),
        "hinglish_case_ids": hinglish_cases,
        "compute_case_count": len(compute_cases),
        "compute_case_ids": compute_cases,
        "check_usage_counts": check_usage,
        "expect_action_value_counts": dict(expect_action_values),
        "expect_lead_case_count": expect_lead_count,
        "cases_added_after_baseline_full_run": new_cases_with_notes,
        "source": "evals/cases.jsonl, evals/cases_src.jsonl, "
        "reports/runs/20260927-175002-baseline-full/eval_report.json",
    }


# ---------------------------------------------------------------------------
# E. Every labelled run
# ---------------------------------------------------------------------------

def _metric_row(markdown: str, metric_name: str) -> tuple[str, str] | None:
    match = re.search(rf"\|\s*{re.escape(metric_name)}\s*\|\s*([^|]+)\|\s*([^|]+)\|", markdown)
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _category_table(markdown: str) -> dict[str, tuple[str, str]]:
    section = re.search(
        r"## By category \(mean pass rate across runs\)\s*\n(.*?)(?=\n## |\Z)", markdown, re.DOTALL
    )
    if not section:
        return {}
    rows = {}
    for line in section.group(1).splitlines():
        m = re.match(r"\|\s*([\w_]+)\s*\|\s*([\d.]+%)\s*\|\s*([\d.]+%)\s*\|", line)
        if m:
            rows[m.group(1)] = (m.group(2), m.group(3))
    return rows


def _run_meta(markdown: str) -> dict[str, str]:
    meta = {}
    for line in markdown.splitlines():
        if line.startswith("Date: "):
            meta["date"] = line.removeprefix("Date: ").strip()
        elif line.startswith("Model: "):
            meta["model"] = line.removeprefix("Model: ").strip()
        elif line.startswith("Cases: "):
            meta["cases_runs"] = line.removeprefix("Cases: ").strip()
    return meta


def _iso_to_ist_display(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    ist = dt.astimezone(_IST)
    return ist.strftime("%Y-%m-%d %H:%M IST")


from datetime import timezone, timedelta  # noqa: E402

_IST = timezone(timedelta(hours=5, minutes=30))


def collect_all_runs() -> dict[str, Any]:
    runs = []
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        summary_path = run_dir / "summary.md"
        if not summary_path.exists():
            continue
        md = _read(summary_path)
        meta = _run_meta(md)
        label = run_dir.name.split("-", 2)[-1] if "-" in run_dir.name else run_dir.name

        row = {
            "run_dir": run_dir.name,
            "label": label,
            "date_ist": _iso_to_ist_display(meta.get("date", "")),
            "model": meta.get("model"),
            "cases_runs": meta.get("cases_runs"),
        }
        for metric_key, metric_name in [
            ("pass_rate", "Pass rate"),
            ("invented_amount_rate", "Invented-amount rate"),
            ("action_accuracy", "Action accuracy"),
            ("ai_disclosure_rate", "AI-disclosure rate"),
            ("latency_p50_ms", "Latency p50 (ms)"),
            ("latency_p95_ms", "Latency p95 (ms)"),
            ("avg_tokens_in", "Avg tokens in"),
            ("avg_tokens_out", "Avg tokens out"),
        ]:
            values = _metric_row(md, metric_name)
            row[f"{metric_key}_mean"] = values[0] if values else "N/A"
            row[f"{metric_key}_worst"] = values[1] if values else "N/A"
        row["category_pass_rates"] = _category_table(md)
        runs.append(row)

    key_labels = ["baseline-full", "final", "final-2", "submission", "ablation-topk"]
    key_runs = {r["label"]: r for r in runs if r["label"] in key_labels}
    all_categories: set[str] = set()
    for r in key_runs.values():
        all_categories.update(r["category_pass_rates"].keys())

    category_comparison = {}
    for cat in sorted(all_categories):
        category_comparison[cat] = {
            label: (key_runs[label]["category_pass_rates"].get(cat, ("N/A", "N/A"))[0] if label in key_runs else "N/A")
            for label in key_labels
        }

    return {
        "all_runs": runs,
        "category_comparison_mean_pass_rate": category_comparison,
        "category_comparison_columns": key_labels,
        "source": "reports/runs/*/summary.md",
    }


# ---------------------------------------------------------------------------
# F. Submission run deep dive
# ---------------------------------------------------------------------------

def collect_submission_deep_dive() -> dict[str, Any]:
    report = _read_json(REPORTS_DIR / "eval_report.json")
    runs = report["runs"]
    total_runs = len(runs)

    case_ids = [r["case_id"] for r in runs[0]]
    per_case: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        for r in run:
            per_case[r["case_id"]].append(r)

    not_3_of_3 = []
    for case_id in case_ids:
        entries = per_case[case_id]
        pass_count = sum(1 for e in entries if e["passed"])
        if pass_count == total_runs:
            continue
        failed_runs_detail = []
        for run_idx, e in enumerate(entries, start=1):
            if e["passed"]:
                continue
            failed_checks = [c["name"] for c in e["checks"] if not c["passed"]]
            last_reply = e["turns"][-1]["response"]["reply"] if e["turns"] else ""
            reason = last_reply[:120]
            failed_runs_detail.append({"run": run_idx, "failed_checks": failed_checks, "reply_excerpt": reason})
        not_3_of_3.append(
            {
                "case_id": case_id,
                "category": entries[0]["category"],
                "pass_ratio": f"{pass_count}/{total_runs}",
                "failed_runs": failed_runs_detail,
            }
        )

    g_counts = {"G1_ai_disclosure": [0, 0], "G2_no_invented_amounts": [0, 0], "G3_length": [0, 0], "G4_sources": [0, 0]}
    invented_amounts_list = []
    handoff_count = 0
    save_lead_count = 0
    escalate_count = 0
    model_calls_hist = Counter()
    latencies_by_category: dict[str, list[float]] = defaultdict(list)
    tokens_in_by_category: dict[str, list[int]] = defaultdict(list)
    tokens_out_by_category: dict[str, list[int]] = defaultdict(list)
    slowest_messages: list[tuple[float, str, int, int]] = []

    for run in runs:
        for r in run:
            for c in r["checks"]:
                if c["name"] in g_counts:
                    g_counts[c["name"]][1] += 1
                    if c["passed"]:
                        g_counts[c["name"]][0] += 1
            for turn_idx, t in enumerate(r["turns"], start=1):
                resp = t["response"]
                usage = resp["usage"]
                model_calls_hist[usage["model_calls"]] += 1
                latencies_by_category[r["category"]].append(usage["latency_ms"])
                tokens_in_by_category[r["category"]].append(usage["prompt_tokens"])
                tokens_out_by_category[r["category"]].append(usage["completion_tokens"])
                slowest_messages.append((usage["latency_ms"], r["case_id"], turn_idx, usage["model_calls"]))
                if resp.get("handoff"):
                    handoff_count += 1
                for action in resp.get("actions", []):
                    if action.get("type") == "save_lead":
                        save_lead_count += 1
                    elif action.get("type") == "escalate":
                        escalate_count += 1

    total_messages = sum(model_calls_hist.values())
    model_calls_pct = {
        k: f"{v} ({v / total_messages * 100:.1f}%)" for k, v in sorted(model_calls_hist.items())
    }

    def _pctl(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        import math

        rank = max(1, math.ceil(p / 100 * len(ordered)))
        return ordered[rank - 1]

    latency_per_category = {
        cat: {"p50": round(_pctl(v, 50), 1), "p95": round(_pctl(v, 95), 1), "n": len(v)}
        for cat, v in sorted(latencies_by_category.items())
    }
    tokens_per_category = {
        cat: {
            "avg_in": round(sum(tokens_in_by_category[cat]) / len(tokens_in_by_category[cat]), 1),
            "avg_out": round(sum(tokens_out_by_category[cat]) / len(tokens_out_by_category[cat]), 1),
        }
        for cat in sorted(tokens_in_by_category)
    }

    slowest_messages.sort(reverse=True)
    slowest_5 = [
        {"case_id": cid, "turn": turn, "latency_ms": round(lat, 1), "model_calls": mc}
        for lat, cid, turn, mc in slowest_messages[:5]
    ]

    # Every invented amount (G2 failures), with which case/run and a reply excerpt.
    for run_idx, run in enumerate(runs, start=1):
        for r in run:
            for c in r["checks"]:
                if c["name"] == "G2_no_invented_amounts" and not c["passed"]:
                    last_reply = r["turns"][-1]["response"]["reply"] if r["turns"] else ""
                    invented_amounts_list.append(
                        {
                            "case_id": r["case_id"],
                            "run": run_idx,
                            "detail": c.get("details", ""),
                            "reply_excerpt": last_reply[:150],
                        }
                    )

    return {
        "cases_not_3_of_3": not_3_of_3,
        "cases_not_3_of_3_count": len(not_3_of_3),
        "guard_check_pass_counts": {
            k: {"passed": v[0], "applicable": v[1]} for k, v in g_counts.items()
        },
        "invented_amounts": invented_amounts_list,
        "model_calls_distribution": model_calls_pct,
        "model_calls_distribution_raw": dict(model_calls_hist),
        "total_messages": total_messages,
        "latency_p50_p95_per_category_ms": latency_per_category,
        "tokens_in_out_per_category": tokens_per_category,
        "slowest_5_messages": slowest_5,
        "handoff_message_count": handoff_count,
        "save_lead_action_count": save_lead_count,
        "escalate_action_count": escalate_count,
        "source": "reports/eval_report.json (submission run, all 3 runs x 76 cases)",
    }


# ---------------------------------------------------------------------------
# H. Guard/safety-net activity (from persisted logs)
# ---------------------------------------------------------------------------

def collect_guard_activity() -> dict[str, Any]:
    # The submission run's live service log was written to an OS temp file,
    # not committed to the repo, and has since been overwritten by later
    # server restarts (ablation run, full-mode restore) -- not recoverable
    # without re-running the service, which this script does not do.
    return {
        "guard_failure_counts_by_type": "N/A (logs not persisted)",
        "correction_retries": "N/A (logs not persisted)",
        "fallback_templates_used": "N/A (logs not persisted)",
        "safety_nets_fired": "N/A (logs not persisted)",
        "auto_escalations_from_step_limit": "N/A (logs not persisted)",
        "note": "The submission run's uvicorn/service log was written to a session-local OS temp "
        "file (not under reports/ or otherwise committed), and was overwritten by subsequent server "
        "restarts for the ablation run and the restore back to full mode. Per instructions, this "
        "script does not re-run the service to regenerate it.",
    }


# ---------------------------------------------------------------------------
# I. Fix history table (from failure_log.md)
# ---------------------------------------------------------------------------

def collect_fix_history() -> dict[str, Any]:
    md = _read(REPORTS_DIR / "failure_log.md")
    fix_headers = re.findall(
        r"^## (Fix \d+[a-z]?(?:/\d+)?[^\n]*|Regression fix:[^\n]*|Hotfix Fix [A-E][^\n]*|"
        r"Part 10A Step 0[^\n]*)\s*$",
        md,
        re.MULTILINE,
    )
    commit_log = _run(["git", "log", "--format=%H|%s"])
    commit_lookup = {}
    for line in commit_log.splitlines():
        h, s = line.split("|", 1)
        commit_lookup[s.strip()] = h[:8]

    fixes = []
    for header in fix_headers:
        section_match = re.search(
            rf"^## {re.escape(header)}\s*\n(.*?)(?=^## |\Z)", md, re.MULTILINE | re.DOTALL
        )
        body = section_match.group(1) if section_match else ""
        cases_match = re.search(r"- Cases: ([^\n]+)", body)
        result_match = re.search(r"- Result: ([^\n]+)", body)
        fixed_match = re.search(r"- Fixed\?\s*([^\n]+)", body)
        commit_match = re.search(r"[Cc]ommit ([0-9a-f]{7,40})", body)
        fixes.append(
            {
                "title": header.strip(),
                "cases": cases_match.group(1).strip() if cases_match else "N/A",
                "result": result_match.group(1).strip() if result_match else "N/A",
                "status": fixed_match.group(1).strip() if fixed_match else "N/A",
                "commit_hash_in_log_text": commit_match.group(1) if commit_match else "N/A (no commit hash cited in text)",
            }
        )

    return {
        "fixes": fixes,
        "source": "reports/failure_log.md (## headers matching Fix N / Regression fix / Hotfix Fix / "
        "Part 10A Step 0 patterns)",
    }


# ---------------------------------------------------------------------------
# J. Model comparison
# ---------------------------------------------------------------------------

def collect_model_comparison() -> dict[str, Any]:
    path = REPORTS_DIR / "model_comparison.md"
    if not path.exists():
        return {"table_markdown": "N/A (reports/model_comparison.md not found)"}
    md = _read(path)
    table_match = re.search(r"\| Model \|.*?\n(?:\|.*\n)+", md)
    return {
        "table_markdown": table_match.group(0).strip() if table_match else "N/A (table not found in file)",
        "source": "reports/model_comparison.md",
    }


# ---------------------------------------------------------------------------
# K. Ablation detail
# ---------------------------------------------------------------------------

def collect_ablation_detail(all_runs: dict[str, Any]) -> dict[str, Any]:
    runs_by_label = {r["label"]: r for r in all_runs["all_runs"]}
    full = runs_by_label.get("submission")
    topk = runs_by_label.get("ablation-topk")
    if not full or not topk:
        return {"note": "N/A (submission or ablation-topk run not found)"}

    metrics = [
        "pass_rate", "invented_amount_rate", "action_accuracy", "ai_disclosure_rate",
        "latency_p50_ms", "latency_p95_ms", "avg_tokens_in", "avg_tokens_out",
    ]
    per_metric = {
        m: {"full_mean": full[f"{m}_mean"], "topk_mean": topk[f"{m}_mean"]} for m in metrics
    }
    all_cats = set(full["category_pass_rates"]) | set(topk["category_pass_rates"])
    per_category = {
        cat: {
            "full_mean": full["category_pass_rates"].get(cat, ("N/A", "N/A"))[0],
            "topk_mean": topk["category_pass_rates"].get(cat, ("N/A", "N/A"))[0],
        }
        for cat in sorted(all_cats)
    }
    return {"per_metric": per_metric, "per_category": per_category, "source": "reports/runs/*/summary.md"}


# ---------------------------------------------------------------------------
# L. Requirement coverage
# ---------------------------------------------------------------------------

def collect_requirement_coverage() -> dict[str, Any]:
    def count_matching(path: Path, pattern: str) -> int:
        return len(re.findall(pattern, _read(path), re.MULTILINE))

    coverage = {}
    checks = [
        ("retrieval", [("tests/test_retrieval.py", r"^def test_")]),
        (
            "lead validation",
            [
                ("tests/test_tools.py", r"^def test_.*(lead|save_lead)"),
                ("tests/test_validation.py", r"^def test_.*(name|phone|email|date)"),
            ],
        ),
        ("rupee-amount extraction", [("tests/test_amounts.py", r"^def test_")]),
        (
            "masking",
            [("tests/test_privacy.py", r"^def test_.*mask"), ("tests/test_stores.py", r"^def test_.*mask")],
        ),
        ("invalid tool args", [("tests/test_tools.py", r"^def test_.*(invalid|argument|rejects|error)")]),
    ]
    for requirement, file_patterns in checks:
        per_file = {}
        for rel_path, pattern in file_patterns:
            full_path = ROOT / rel_path
            if full_path.exists():
                per_file[rel_path] = count_matching(full_path, pattern)
        coverage[requirement] = {"test_files": per_file, "total": sum(per_file.values())}

    return {
        "coverage": coverage,
        "source": "regex match on test function names in tests/*.py (patterns documented per requirement above)",
    }


# ---------------------------------------------------------------------------
# M. Timeline per Part
# ---------------------------------------------------------------------------

_PART_PATTERNS = [
    ("Part 0", r"^Part 0\b"),
    ("Part 1", r"^Part 1:"),
    ("Part 2", r"^Part 2:"),
    ("Part 3", r"^Part 3:"),
    ("Part 4", r"^Part 4:"),
    ("Part 5", r"^Part 5[abc]:"),
    ("Part 6", r"^Part 6:"),
    ("Part 7", r"^Part 7:"),
    ("Part 8", r"^Part 8:"),
    (
        "Part 9 (incl. Fix 1-13 + resolver regression + round 2)",
        r"^Part 9\b|^Fix \d|^Fix arith-01|^Round 2\b",
    ),
    ("Bonus", r"^Bonus:"),
    (
        "Chat page + language guard (unlabelled Part)",
        r"^Guard: retry|^Chat page:|^Add scripts/inspect_failures",
    ),
    ("Hotfix round", r"^Hotfix"),
    ("Part 10A", r"^Part 10A|^Evals: add long-session|^Post-submission check"),
]


def collect_timeline() -> dict[str, Any]:
    log = _run(["git", "log", "--format=%H|%ai|%s"]).splitlines()
    commits = []
    for line in log:
        h, date, subj = line.split("|", 2)
        commits.append((h, date, subj))
    commits.reverse()  # oldest first

    timeline = []
    matched_hashes: set[str] = set()
    for label, pattern in _PART_PATTERNS:
        regex = re.compile(pattern)
        matches = [(h, d, s) for h, d, s in commits if regex.search(s)]
        matched_hashes.update(h for h, _, _ in matches)
        if matches:
            timeline.append(
                {
                    "part": label,
                    "commit_count": len(matches),
                    "first_commit": {"date": matches[0][1], "subject": matches[0][2]},
                    "last_commit": {"date": matches[-1][1], "subject": matches[-1][2]},
                }
            )
        else:
            timeline.append({"part": label, "commit_count": 0, "first_commit": "N/A", "last_commit": "N/A"})

    unmatched = [{"hash": h[:8], "date": d, "subject": s} for h, d, s in commits if h not in matched_hashes]

    return {
        "timeline": timeline,
        "unmatched_commit_count": len(unmatched),
        "unmatched_commits": unmatched,
        "source": "git log, matched against the regex patterns listed in scripts/collect_report_facts.py "
        "(_PART_PATTERNS) -- a commit can match at most one bucket, first pattern listed wins",
    }


# ---------------------------------------------------------------------------
# N. Unverified / inconsistent items
# ---------------------------------------------------------------------------

def collect_inconsistencies(data_lexicon: dict[str, Any], all_runs: dict[str, Any]) -> dict[str, Any]:
    findings = []

    # SKU count check: current TECHNICAL_REPORT.md claims "12 SKUs".
    actual_sku_count = data_lexicon["sku_count"]
    report_md_path = ROOT / "docs" / "TECHNICAL_REPORT.md"
    if report_md_path.exists():
        report_text = _read(report_md_path)
        claimed = re.findall(r"(\d+)\s+SKUs", report_text)
        for c in claimed:
            if int(c) != actual_sku_count:
                findings.append(
                    {
                        "item": "SKU count",
                        "claimed": f"{c} SKUs (docs/TECHNICAL_REPORT.md)",
                        "actual": f"{actual_sku_count} SKUs (data/prices.csv via meher_agent.knowledge)",
                        "note": "docs/TECHNICAL_REPORT.md understates the SKU count.",
                    }
                )

    # unknown 27.8% -> 88.9% (Fix 3) vs later runs showing 100%.
    runs_by_label = {r["label"]: r for r in all_runs["all_runs"]}
    unknown_progression = {
        label: runs_by_label[label]["category_pass_rates"].get("unknown", ("N/A", "N/A"))[0]
        for label in ("baseline-full", "final", "final-2", "submission")
        if label in runs_by_label
    }
    if any(v == "100.0%" for v in unknown_progression.values()):
        findings.append(
            {
                "item": "unknown category: Fix 3's claimed after-number vs later runs",
                "claimed": "Fix 3 entry in failure_log.md: unknown 27.8% -> 88.9% (mean), with unknown-04 "
                "explicitly left as a residual 2/3 failure, no further fix entry for it",
                "actual": f"category pass rate by run: {unknown_progression}",
                "note": "unknown reached 100% in later runs (final onward) without an explicit failure_log.md "
                "entry crediting a specific fix for unknown-04's residual; likely a side effect of a later "
                "prompt/grounding change (e.g. Fix 4's refusal-phrasing rules or Fix 9's item grounding), but "
                "the log does not state this explicitly -- flagged as a documentation gap, not a numeric error.",
            }
        )

    return {"findings": findings, "count": len(findings)}


# ---------------------------------------------------------------------------
# Render markdown
# ---------------------------------------------------------------------------

def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def render_markdown(d: dict[str, Any]) -> str:
    lines = ["# Report data pack (facts only)", "", f"Generated: {datetime.now().isoformat()} by `scripts/collect_report_facts.py`. Every number below is sourced from a file/command noted inline; nothing is invented or interpreted.", ""]

    # Step 0
    lines += ["## Step 0: Privacy check", "", f"Source: {d['privacy_check']['source']}", "", f"**Verdict: {d['privacy_check']['verdict']}**", ""]
    for fr in d["privacy_check"]["failing_runs"]:
        lines.append(f"- run {fr['run']}, `{fr['case_id']}`: failed [{', '.join(fr['failed_checks'])}]; contains phone/+91: {fr['contains_phone_or_+91']}")
        lines.append(f"  reply: {fr['reply']!r}")
    lines.append("")

    # A
    a = d["A_project_stats"]
    lines += ["## A. Project stats", "", f"Source: {a['source']}", ""]
    lines.append("**Lines of code:**")
    for module, files in a["loc_per_module"].items():
        lines.append(f"- `{module}` (total {a['loc_totals'][module]}):")
        for f, n in files.items():
            lines.append(f"  - {f}: {n}")
    lines.append(f"- Grand total: {a['loc_totals']['grand_total']}")
    lines.append("")
    lines.append(f"**Tests:** {a['test_count_total']} collected (pytest); sum over test files: {a['test_count_per_file_sum']}")
    for f, n in a["test_count_per_file"].items():
        lines.append(f"- {f}: {n}")
    lines.append("")
    lines.append(f"**Commits:** {a['commit_count']} total, first {a['first_commit_date']}, last {a['last_commit_date']}")
    lines.append(f"**Python version:** {a['python_version']}")
    lines.append("**Dependencies (requirements.txt):**")
    for r in a["requirements_txt"]:
        lines.append(f"- {r}")
    lines.append("")

    # B
    b = d["B_data_and_lexicon"]
    lines += ["## B. Data & lexicon", "", f"Source: {b['source']}", ""]
    lines.append(f"- SKUs: {b['sku_count']}")
    lines.append(f"- Policy sections: {b['policy_section_count']} ({', '.join(b['policy_section_ids'])})")
    lines.append(f"- Business sections: {b['business_section_count']} ({', '.join(b['business_section_ids'])})")
    lines.append(f"- Valid source IDs total: {b['valid_source_id_count']}")
    lines.append(f"- Lexicon product aliases total: {b['lexicon_product_alias_total']} (per SKU: {b['lexicon_product_alias_counts_per_sku']})")
    lines.append(f"- Lexicon section aliases: {b['lexicon_section_alias_counts']}")
    lines.append(f"- Hinglish markers: {b['lexicon_hinglish_marker_count']}")
    lines.append(f"- English function words: {b['lexicon_english_function_word_count']}")
    lines.append(f"- [intents] list sizes: {b['lexicon_intents_sizes']}")
    lines.append(f"- [sizes] category word counts: {b['lexicon_sizes_categories']}")
    lines.append("")

    # C
    c = d["C_config_values"]
    lines += ["## C. Config values", "", f"Source: {c['source']}", ""]
    for section in ("llm", "agent", "reply", "retrieval", "policy", "eval"):
        lines.append(f"**[{section}]**")
        for k, v in c[section].items():
            lines.append(f"- {k} = {v}")
    lines.append("")

    # D
    dd = d["D_case_set"]
    lines += ["## D. Case set", "", f"Source: {dd['source']}", ""]
    lines.append(f"- Total cases: {dd['total_cases']}")
    lines.append(f"- Per category: {dd['per_category']}")
    lines.append(f"- Multi-turn cases: {dd['multi_turn_case_count']} (max turns: {dd['max_turns']}) -- {dd['multi_turn_case_ids']}")
    lines.append(f"- Cases with Devanagari text: {dd['devanagari_case_count']} -- {dd['devanagari_case_ids']}")
    lines.append(f"- Hinglish-category cases: {dd['hinglish_case_count']} -- {dd['hinglish_case_ids']}")
    lines.append(f"- Cases using `compute` (in cases_src.jsonl): {dd['compute_case_count']} -- {dd['compute_case_ids']}")
    lines.append(f"- Check usage counts: {dd['check_usage_counts']}")
    lines.append(f"- expect_action value counts: {dd['expect_action_value_counts']}")
    lines.append(f"- expect_lead case count: {dd['expect_lead_case_count']}")
    lines.append("- Cases added after the baseline-full run:")
    for c2 in dd["cases_added_after_baseline_full_run"]:
        lines.append(f"  - `{c2['id']}`: {c2['note']}")
    lines.append("")

    # E
    e = d["E_all_runs"]
    lines += ["## E. Every labelled run", "", f"Source: {e['source']}", ""]
    headers = ["label", "date (IST)", "cases x runs", "pass% mean/worst", "invented% mean/worst", "action% mean/worst", "AI-discl% mean/worst", "p50/p95 ms", "tokens in/out"]
    rows = []
    for r in e["all_runs"]:
        rows.append([
            r["label"], r["date_ist"], r["cases_runs"],
            f"{r['pass_rate_mean']}/{r['pass_rate_worst']}",
            f"{r['invented_amount_rate_mean']}/{r['invented_amount_rate_worst']}",
            f"{r['action_accuracy_mean']}/{r['action_accuracy_worst']}",
            f"{r['ai_disclosure_rate_mean']}/{r['ai_disclosure_rate_worst']}",
            f"{r['latency_p50_ms_mean']}/{r['latency_p95_ms_mean']}",
            f"{r['avg_tokens_in_mean']}/{r['avg_tokens_out_mean']}",
        ])
    lines.append(_md_table(headers, rows))
    lines.append("")
    lines.append("**Per-category pass rate (mean), key runs:**")
    cat_headers = ["category"] + e["category_comparison_columns"]
    cat_rows = [[cat] + [vals.get(col, "N/A") for col in e["category_comparison_columns"]] for cat, vals in e["category_comparison_mean_pass_rate"].items()]
    lines.append(_md_table(cat_headers, cat_rows))
    lines.append("")

    # F
    f = d["F_submission_deep_dive"]
    lines += ["## F. Submission run deep dive", "", f"Source: {f['source']}", ""]
    lines.append(f"**Cases not 3/3 ({f['cases_not_3_of_3_count']}):**")
    for item in f["cases_not_3_of_3"]:
        lines.append(f"- `{item['case_id']}` ({item['category']}, {item['pass_ratio']}):")
        for fr in item["failed_runs"]:
            lines.append(f"  - run {fr['run']}: failed {fr['failed_checks']}; reply: {fr['reply_excerpt']!r}")
    lines.append("")
    lines.append(f"**Guard check pass counts:** {f['guard_check_pass_counts']}")
    lines.append("")
    lines.append(f"**Every invented amount ({len(f['invented_amounts'])}):**")
    for ia in f["invented_amounts"]:
        lines.append(f"- `{ia['case_id']}` run {ia['run']}: {ia['detail']}; reply: {ia['reply_excerpt']!r}")
    lines.append("")
    lines.append(f"**model_calls distribution** (over {f['total_messages']} messages): {f['model_calls_distribution']}")
    lines.append("")
    lines.append(f"**Latency p50/p95 per category (ms):** {f['latency_p50_p95_per_category_ms']}")
    lines.append(f"**Tokens in/out per category:** {f['tokens_in_out_per_category']}")
    lines.append("**Slowest 5 messages:**")
    for m in f["slowest_5_messages"]:
        lines.append(f"- `{m['case_id']}` turn {m['turn']}: {m['latency_ms']} ms, {m['model_calls']} model_calls")
    lines.append(f"**Handoff-triggering messages:** {f['handoff_message_count']}")
    lines.append(f"**save_lead actions:** {f['save_lead_action_count']}  **escalate actions:** {f['escalate_action_count']}")
    lines.append("")

    # G
    lines += ["## G. Privacy failure evidence", "", "See Step 0 above (same data, restated here per the requested section lettering).", ""]

    # H
    h = d["H_guard_activity"]
    lines += ["## H. Guard and safety-net activity (submission run)", "", h["note"], ""]
    for k in ("guard_failure_counts_by_type", "correction_retries", "fallback_templates_used", "safety_nets_fired", "auto_escalations_from_step_limit"):
        lines.append(f"- {k}: {h[k]}")
    lines.append("")

    # I
    i = d["I_fix_history"]
    lines += ["## I. Fix history", "", f"Source: {i['source']}", ""]
    rows = [[fx["title"], fx["cases"], fx["result"], fx["commit_hash_in_log_text"], fx["status"]] for fx in i["fixes"]]
    lines.append(_md_table(["fix", "cases", "result (before -> after)", "commit hash (cited in text)", "status"], rows))
    lines.append("")

    # J
    j = d["J_model_comparison"]
    lines += ["## J. Model comparison", "", f"Source: {j.get('source', 'N/A')}", "", j["table_markdown"], ""]

    # K
    k = d["K_ablation"]
    lines += ["## K. Ablation: full vs top-k", ""]
    if "note" in k:
        lines.append(k["note"])
    else:
        lines.append(f"Source: {k['source']}")
        lines.append("")
        rows = [[m, v["full_mean"], v["topk_mean"]] for m, v in k["per_metric"].items()]
        lines.append(_md_table(["metric", "full (submission)", "topk (ablation)"], rows))
        lines.append("")
        rows = [[cat, v["full_mean"], v["topk_mean"]] for cat, v in k["per_category"].items()]
        lines.append(_md_table(["category", "full (submission)", "topk (ablation)"], rows))
    lines.append("")

    # L
    lreq = d["L_requirement_coverage"]
    lines += ["## L. Requirement coverage", "", f"Source: {lreq['source']}", ""]
    for req, cov in lreq["coverage"].items():
        lines.append(f"- **{req}**: {cov['total']} tests -- {cov['test_files']}")
    lines.append("")

    # M
    m = d["M_timeline"]
    lines += ["## M. Timeline per Part", "", f"Source: {m['source']}", ""]
    rows = []
    for t in m["timeline"]:
        if t["commit_count"] == 0:
            rows.append([t["part"], "0", "N/A", "N/A"])
        else:
            rows.append([t["part"], str(t["commit_count"]), t["first_commit"]["date"], t["last_commit"]["date"]])
    lines.append(_md_table(["part", "commits", "first commit", "last commit"], rows))
    lines.append(f"\nUnmatched commits: {m['unmatched_commit_count']}")
    for uc in m["unmatched_commits"]:
        lines.append(f"- {uc['hash']} {uc['date']} {uc['subject']}")
    lines.append("")

    # N
    n = d["N_inconsistencies"]
    lines += ["## N. Unverified / inconsistent items", ""]
    if not n["findings"]:
        lines.append("None found.")
    for finding in n["findings"]:
        lines.append(f"- **{finding['item']}**")
        lines.append(f"  - Claimed: {finding['claimed']}")
        lines.append(f"  - Actual: {finding['actual']}")
        lines.append(f"  - Note: {finding['note']}")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    all_runs = collect_all_runs()
    data_lexicon = collect_data_and_lexicon()

    d = {
        "privacy_check": collect_privacy_check(),
        "A_project_stats": collect_project_stats(),
        "B_data_and_lexicon": data_lexicon,
        "C_config_values": collect_config_values(),
        "D_case_set": collect_case_set(),
        "E_all_runs": all_runs,
        "F_submission_deep_dive": collect_submission_deep_dive(),
        "H_guard_activity": collect_guard_activity(),
        "I_fix_history": collect_fix_history(),
        "J_model_comparison": collect_model_comparison(),
        "K_ablation": collect_ablation_detail(all_runs),
        "L_requirement_coverage": collect_requirement_coverage(),
        "M_timeline": collect_timeline(),
    }
    d["N_inconsistencies"] = collect_inconsistencies(data_lexicon, all_runs)

    OUT_JSON.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text(render_markdown(d), encoding="utf-8")
    print(f"Wrote {OUT_MD} and {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
