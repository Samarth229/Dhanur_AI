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
    import os

    sys.path.insert(0, str(SRC_DIR))
    os.environ["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + os.environ.get("PYTHONPATH", "")

    import uvicorn

    from meher_agent.config import settings

    if args.reload:
        uvicorn.run(
            "meher_agent.api:create_app",
            factory=True,
            host=settings.server.host,
            port=settings.server.port,
            reload=True,
            app_dir=str(SRC_DIR),
        )
    else:
        from meher_agent.api import create_app

        uvicorn.run(create_app(), host=settings.server.host, port=settings.server.port)
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    return subprocess.call([sys.executable, "-m", "pytest", *args.extra_args])


def cmd_eval(args: argparse.Namespace) -> int:
    import os

    sys.path.insert(0, str(SRC_DIR))
    sys.path.insert(0, str(PROJECT_ROOT))
    from meher_agent.config import settings
    from evals_harness.runner import run_eval

    base_url = args.base_url or os.environ.get("EVAL_BASE_URL") or settings.eval.base_url
    return run_eval(
        args.cases,
        settings,
        runs=args.runs,
        base_url=base_url,
        label=args.label,
    )


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


def cmd_quote(args: argparse.Namespace) -> int:
    import json

    sys.path.insert(0, str(SRC_DIR))
    from meher_agent.pricing import PricingError, quote_order

    items = []
    for spec in args.item:
        name, amount, unit = spec.rsplit(":", 2)
        items.append({"item": name, "amount": float(amount), "unit": unit})

    try:
        quote = quote_order(items, distance_km=args.distance, delivery_date=args.date)
    except PricingError as exc:
        print(f"{exc.code}: {exc.message}")
        return 1

    print(quote.to_tool_text())
    print()
    print(
        json.dumps(
            {
                "lines": [vars(line) for line in quote.lines],
                "subtotal": quote.subtotal,
                "giftbox_count": quote.giftbox_count,
                "giftbox_subtotal": quote.giftbox_subtotal,
                "discount_amount": quote.discount_amount,
                "goods_total": quote.goods_total,
                "delivery": vars(quote.delivery),
                "grand_total": quote.grand_total,
                "sweets_kg": quote.sweets_kg,
                "bulk": vars(quote.bulk),
                "cod_allowed": quote.cod_allowed,
                "preorder_closed": quote.preorder_closed,
                "notes": quote.notes,
                "source_ids": quote.source_ids,
                "allowed_amounts": quote.allowed_amounts,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    import uuid

    sys.path.insert(0, str(SRC_DIR))
    from meher_agent.agent import Agent
    from meher_agent.llm import LLMClient

    conversation_id = args.conversation_id or str(uuid.uuid4())
    print(f"Conversation id: {conversation_id}")
    print("Type your message and press Enter. Ctrl+C to quit.\n")

    agent = Agent(llm=LLMClient())
    while True:
        try:
            message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not message:
            continue

        result = agent.handle(conversation_id, message)
        print(f"Bot: {result.reply}")
        print(f"  sources: {result.sources}")
        print(f"  actions: {result.actions}")
        print(f"  handoff: {result.handoff}")
        print(f"  model_calls: {result.usage['model_calls']}  latency_ms: {result.latency_ms:.0f}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Meher Sweets agent management commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_run = subparsers.add_parser("run", help="Start the service.")
    p_run.add_argument("--reload", action="store_true", help="Auto-reload on code changes (development).")
    p_run.set_defaults(func=cmd_run)

    p_test = subparsers.add_parser("test", help="Run the test suite.")
    p_test.set_defaults(func=cmd_test)

    p_eval = subparsers.add_parser("eval", help="Run the eval harness.")
    p_eval.add_argument("--cases", required=True, help="Path to eval cases file.")
    p_eval.add_argument("--runs", type=int, default=None, help="Number of runs (default from config).")
    p_eval.add_argument("--base-url", default=None, help="Service base URL (default from config / EVAL_BASE_URL).")
    p_eval.add_argument("--label", default=None, help="Label for this eval run.")
    p_eval.set_defaults(func=cmd_eval)

    p_check = subparsers.add_parser("check-llm", help="Verify the LLM endpoint works.")
    p_check.set_defaults(func=cmd_check_llm)

    p_retrieve = subparsers.add_parser("retrieve", help="Debug: show retrieval hits for a message.")
    p_retrieve.add_argument("message", help="Customer message to test retrieval against.")
    p_retrieve.set_defaults(func=cmd_retrieve)

    p_quote = subparsers.add_parser("quote", help="Debug: price an order.")
    p_quote.add_argument(
        "--item", action="append", required=True, help='Item as "name:amount:unit", repeatable.'
    )
    p_quote.add_argument("--distance", type=float, default=None, help="Delivery distance in km.")
    p_quote.add_argument("--date", default=None, help="Delivery date, YYYY-MM-DD.")
    p_quote.set_defaults(func=cmd_quote)

    p_chat = subparsers.add_parser("chat", help="Interactive terminal chat with the agent.")
    p_chat.add_argument("--conversation-id", default=None, help="Reuse a specific conversation id.")
    p_chat.set_defaults(func=cmd_chat)

    args, extra_args = parser.parse_known_args()
    args.extra_args = extra_args
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
