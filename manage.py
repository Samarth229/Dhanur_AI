"""Cross-platform command runner for the Meher Sweets agent project."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

# Ensure Devanagari and other non-ASCII output print correctly regardless of
# the terminal's default codepage (notably cp1252 on Windows).
sys.stdout.reconfigure(encoding="utf-8")


def cmd_run(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(SRC_DIR))
    from meher_agent.config import settings

    try:
        import uvicorn
        from fastapi import FastAPI
    except ImportError:
        print("service not built yet")
        return 0

    app = FastAPI(title="Meher Sweets Agent")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    uvicorn.run(app, host=settings.server.host, port=settings.server.port)
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    return subprocess.call([sys.executable, "-m", "pytest", *args.extra_args])


def cmd_eval(args: argparse.Namespace) -> int:
    print("harness not built yet")
    return 0


def cmd_check_llm(args: argparse.Namespace) -> int:
    return subprocess.call([sys.executable, str(PROJECT_ROOT / "scripts" / "check_llm.py")])


def cmd_retrieve(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(SRC_DIR))
    from meher_agent.retrieval import retrieve

    hits = retrieve(args.message)
    if not hits:
        print("No hits (out of scope, or below min_score).")
        return 0

    for hit in hits:
        terms = ", ".join(hit.matched_terms)
        print(f"{hit.source_id}  score={hit.score:.1f}  matched_terms=[{terms}]")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Meher Sweets agent management commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_run = subparsers.add_parser("run", help="Start the service.")
    p_run.set_defaults(func=cmd_run)

    p_test = subparsers.add_parser("test", help="Run the test suite.")
    p_test.set_defaults(func=cmd_test)

    p_eval = subparsers.add_parser("eval", help="Run the eval harness.")
    p_eval.add_argument("--cases", required=False, help="Path to eval cases file.")
    p_eval.set_defaults(func=cmd_eval)

    p_check = subparsers.add_parser("check-llm", help="Verify the LLM endpoint works.")
    p_check.set_defaults(func=cmd_check_llm)

    p_retrieve = subparsers.add_parser("retrieve", help="Debug: show retrieval hits for a message.")
    p_retrieve.add_argument("message", help="Customer message to test retrieval against.")
    p_retrieve.set_defaults(func=cmd_retrieve)

    args, extra_args = parser.parse_known_args()
    args.extra_args = extra_args
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
