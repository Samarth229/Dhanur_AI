"""Sanity-checks the configured LLM endpoint end to end.

Sends one plain chat completion and one tool-calling request (with a
dummy tool) through the OpenAI-compatible client, then reports latency
and token usage for each, plus whether tool calling worked.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openai import OpenAI

from meher_agent.config import get_llm_credentials, settings

DUMMY_TOOL = {
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "Returns the current time for a given city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name."},
            },
            "required": ["city"],
        },
    },
}


def main() -> int:
    try:
        creds = get_llm_credentials()
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 1

    client = OpenAI(
        base_url=creds.base_url,
        api_key=creds.api_key,
        timeout=settings.llm.request_timeout_s,
    )

    print(f"Model: {creds.model}")
    print(f"Base URL: {creds.base_url}")
    print()

    # 1. Plain chat completion.
    print("--- Plain chat completion ---")
    start = time.monotonic()
    try:
        resp = client.chat.completions.create(
            model=creds.model,
            messages=[{"role": "user", "content": "Say hello in exactly one word."}],
            temperature=settings.llm.temperature,
            max_tokens=settings.llm.max_tokens,
        )
    except Exception as exc:
        print(f"FAIL: chat completion request failed: {exc}")
        return 1
    latency_ms = (time.monotonic() - start) * 1000
    print(f"Latency: {latency_ms:.0f} ms")
    print(f"Reply: {resp.choices[0].message.content!r}")
    if resp.usage:
        print(
            f"Tokens: prompt={resp.usage.prompt_tokens} "
            f"completion={resp.usage.completion_tokens} "
            f"total={resp.usage.total_tokens}"
        )
    print()

    # 2. Tool-calling request.
    print("--- Tool-calling request ---")
    start = time.monotonic()
    try:
        tool_resp = client.chat.completions.create(
            model=creds.model,
            messages=[
                {
                    "role": "user",
                    "content": "What time is it in Mumbai? Use the available tool.",
                }
            ],
            tools=[DUMMY_TOOL],
            temperature=settings.llm.temperature,
            max_tokens=settings.llm.max_tokens,
        )
    except Exception as exc:
        print(f"FAIL: tool-calling request failed: {exc}")
        return 1
    latency_ms = (time.monotonic() - start) * 1000
    print(f"Latency: {latency_ms:.0f} ms")

    tool_calls = tool_resp.choices[0].message.tool_calls
    tool_calling_works = bool(tool_calls)
    if tool_calling_works:
        for call in tool_calls:
            print(f"Tool call: {call.function.name}({call.function.arguments})")
    else:
        print(f"No tool call made. Reply: {tool_resp.choices[0].message.content!r}")

    if tool_resp.usage:
        print(
            f"Tokens: prompt={tool_resp.usage.prompt_tokens} "
            f"completion={tool_resp.usage.completion_tokens} "
            f"total={tool_resp.usage.total_tokens}"
        )
    print()

    print(f"Tool calling works: {tool_calling_works}")
    print("RESULT: PASS" if tool_calling_works else "RESULT: FAIL (no tool call returned)")
    return 0 if tool_calling_works else 1


if __name__ == "__main__":
    raise SystemExit(main())
