"""Live smoke test: runs the 13 seed cases through Agent.handle directly.

Not a formal eval (that's Part 7) -- just a manual sanity check with a real
Ollama model, one fresh conversation per case, printing reply/sources/
actions/handoff/model_calls/latency for a human to eyeball.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from meher_agent.agent import Agent
from meher_agent.config import settings
from meher_agent.llm import LLMClient


def load_seed_cases() -> list[dict]:
    cases = []
    with open(settings.paths.evals_dir / "seed_cases.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def main() -> int:
    cases = load_seed_cases()
    llm = LLMClient()

    for case in cases:
        agent = Agent(llm=llm)  # fresh stores/conversation store per case
        conversation_id = case["id"]
        result = None
        for turn in case["turns"]:
            result = agent.handle(conversation_id, turn)

        print(f"=== {case['id']} ===")
        print(f"Turns: {case['turns']}")
        print(f"Reply: {result.reply}")
        print(f"Sources: {result.sources}")
        print(f"Actions: {result.actions}")
        print(f"Handoff: {result.handoff}")
        print(f"Model calls: {result.usage['model_calls']}  Latency: {result.latency_ms:.0f} ms")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
