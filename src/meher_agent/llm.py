"""A thin, robust wrapper around any OpenAI-compatible chat completions API.

Handles the quirks of small/local models: <think> blocks, tool calls
written as plain text instead of using the native tool-calling API, and
missing token usage. A Protocol lets tests inject a FakeLLM instead of
talking to a real model.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import APIConnectionError, APITimeoutError, OpenAI

from meher_agent.config import Settings, get_llm_credentials, settings as default_settings

_THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_TOOL_CALL_TAG_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_BARE_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class LLMUnavailable(Exception):
    pass


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    estimated_tokens: bool = False


class LLMClientProtocol(Protocol):
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse: ...


def _strip_think(content: str) -> str:
    return _THINK_RE.sub("", content).strip()


def _extract_text_tool_call(content: str, known_tool_names: set[str]) -> tuple[str, ToolCall | None]:
    """Looks for a tool call written as text instead of via the native API.

    Returns (remaining_content, tool_call_or_none).
    """
    match = _TOOL_CALL_TAG_RE.search(content)
    if match:
        payload = match.group(1)
        remaining = (content[: match.start()] + content[match.end() :]).strip()
        call = _parse_json_tool_call(payload, known_tool_names)
        if call is not None:
            return remaining, call

    match = _BARE_JSON_RE.search(content)
    if match:
        call = _parse_json_tool_call(match.group(0), known_tool_names)
        if call is not None:
            remaining = (content[: match.start()] + content[match.end() :]).strip()
            return remaining, call

    return content, None


def _parse_json_tool_call(payload: str, known_tool_names: set[str]) -> ToolCall | None:
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("name")
    if name not in known_tool_names:
        return None
    arguments = obj.get("arguments", {})
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments)
    return ToolCall(id=f"text-call-{name}", name=name, arguments=arguments)


class LLMClient:
    def __init__(self, settings_obj: Settings | None = None):
        self.settings = settings_obj or default_settings
        creds = get_llm_credentials()
        self.model = creds.model
        self._client = OpenAI(
            base_url=creds.base_url,
            api_key=creds.api_key,
            timeout=self.settings.llm.request_timeout_s,
        )

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        known_tool_names = {t["function"]["name"] for t in tools}
        start = time.monotonic()
        try:
            resp = self._call_with_one_retry(messages, tools)
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMUnavailable(str(exc)) from exc
        latency_ms = (time.monotonic() - start) * 1000

        message = resp.choices[0].message
        content = _strip_think(message.content or "")

        tool_calls = [
            ToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments)
            for call in (message.tool_calls or [])
        ]

        if not tool_calls and content:
            content, text_call = _extract_text_tool_call(content, known_tool_names)
            if text_call is not None:
                tool_calls = [text_call]

        usage = resp.usage
        estimated = usage is None
        prompt_tokens = usage.prompt_tokens if usage else len(_flatten_messages(messages)) // 4
        completion_tokens = usage.completion_tokens if usage else len(content) // 4

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            estimated_tokens=estimated,
        )

    def _call_with_one_retry(self, messages, tools):
        try:
            return self._request(messages, tools)
        except (APIConnectionError, APITimeoutError):
            return self._request(messages, tools)

    def _request(self, messages, tools):
        return self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=self.settings.llm.temperature,
            max_tokens=self.settings.llm.max_tokens,
        )


def _flatten_messages(messages: list[dict[str, Any]]) -> str:
    return " ".join(str(m.get("content") or "") for m in messages)
