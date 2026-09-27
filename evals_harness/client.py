"""Thin HTTP client for the eval harness. Talks to the service ONLY over
HTTP -- never imports agent/tools/llm/api. Never raises: every failure
becomes a structured ChatResult with error set.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ChatResult:
    ok: bool
    status_code: int | None
    body: dict[str, Any] | None
    latency_ms: float
    error: str | None = None


class EvalClient:
    def __init__(self, base_url: str, timeout_s: float, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout_s, transport=transport)

    def close(self) -> None:
        self._client.close()

    def get_health(self) -> ChatResult:
        start = time.monotonic()
        try:
            resp = self._client.get("/health")
        except httpx.HTTPError as exc:
            return ChatResult(ok=False, status_code=None, body=None, latency_ms=0.0, error=str(exc))
        latency_ms = (time.monotonic() - start) * 1000
        try:
            body = resp.json()
        except ValueError:
            body = None
        return ChatResult(ok=resp.status_code == 200, status_code=resp.status_code, body=body, latency_ms=latency_ms)

    def post_chat(self, conversation_id: str, message: str) -> ChatResult:
        start = time.monotonic()
        try:
            resp = self._client.post(
                "/chat", json={"conversation_id": conversation_id, "message": message}
            )
        except httpx.TimeoutException as exc:
            return ChatResult(
                ok=False, status_code=None, body=None,
                latency_ms=(time.monotonic() - start) * 1000, error=f"timeout: {exc}",
            )
        except httpx.HTTPError as exc:
            return ChatResult(
                ok=False, status_code=None, body=None,
                latency_ms=(time.monotonic() - start) * 1000, error=f"http error: {exc}",
            )

        latency_ms = (time.monotonic() - start) * 1000
        if resp.status_code != 200:
            return ChatResult(
                ok=False, status_code=resp.status_code, body=None,
                latency_ms=latency_ms, error=f"HTTP {resp.status_code}",
            )
        try:
            body = resp.json()
        except ValueError as exc:
            return ChatResult(
                ok=False, status_code=resp.status_code, body=None,
                latency_ms=latency_ms, error=f"invalid JSON response: {exc}",
            )
        return ChatResult(ok=True, status_code=200, body=body, latency_ms=latency_ms)
