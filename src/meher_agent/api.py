"""FastAPI service exposing the agent over HTTP.

The agent is synchronous (the openai client blocks), so /chat handlers are
plain `def` functions -- FastAPI runs those in a threadpool automatically.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from meher_agent.agent import Agent
from meher_agent.config import Settings, get_llm_credentials, settings as default_settings
from meher_agent.llm import LLMClient, LLMUnavailable
from meher_agent.logging_setup import setup_logging

logger = logging.getLogger(__name__)

_CONVERSATION_ID_RE = r"^[A-Za-z0-9_-]{1,100}$"
_CHAT_PAGE_PATH = Path(__file__).resolve().parent / "static" / "chat.html"


class ChatRequest(BaseModel):
    conversation_id: str = Field(pattern=_CONVERSATION_ID_RE)
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    sources: list[str]
    actions: list[dict[str, Any]]
    handoff: bool
    usage: dict[str, Any]


class _ConversationLocks:
    """One lock per conversation_id, created lazily and kept forever.

    Conversation counts for this project are small and bounded (a take-home
    eval, not a production-scale service), so unbounded retention is the
    simplest correct choice -- no LRU eviction complexity or race window.
    """

    def __init__(self) -> None:
        self._meta_lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def get(self, conversation_id: str) -> threading.Lock:
        with self._meta_lock:
            lock = self._locks.get(conversation_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[conversation_id] = lock
            return lock


def _warm_up(agent: Agent) -> None:
    try:
        agent.llm.chat(
            [{"role": "user", "content": "Hello"}],
            tools=[],
        )
    except Exception as exc:  # noqa: BLE001 - warmup must never crash startup
        logger.warning("LLM warm-up failed (server will still start): %s", exc)


def create_app(settings: Settings | None = None, agent: Agent | None = None) -> FastAPI:
    settings = settings or default_settings
    setup_logging(settings)

    if agent is None:
        try:
            get_llm_credentials()
        except RuntimeError as exc:
            logger.error("Cannot start: %s", exc)
            print(f"FATAL: {exc}", file=sys.stderr)
            sys.exit(1)
        agent = Agent(llm=LLMClient(settings), settings=settings)

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        if settings.server.warmup_on_start:
            _warm_up(agent)
        yield

    app = FastAPI(title="Meher Sweets Agent", lifespan=_lifespan)
    app.state.agent = agent
    app.state.settings = settings
    app.state.locks = _ConversationLocks()

    @app.exception_handler(Exception)
    def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"error": "internal error"})

    @app.post("/chat", response_model=ChatResponse)
    def chat(payload: ChatRequest) -> ChatResponse:
        lock = app.state.locks.get(payload.conversation_id)
        with lock:
            start = time.monotonic()
            status = "ok"
            try:
                result = agent.handle(payload.conversation_id, payload.message)
            except Exception:
                status = "error"
                raise
            finally:
                latency_ms = (time.monotonic() - start) * 1000
                logger.info(
                    "chat conversation_id=%s message_len=%s status=%s latency_ms=%.0f",
                    payload.conversation_id,
                    len(payload.message),
                    status,
                    latency_ms,
                )

        usage = {**result.usage, "latency_ms": result.latency_ms}
        return ChatResponse(
            reply=result.reply,
            sources=result.sources,
            actions=result.actions,
            handoff=result.handoff,
            usage=usage,
        )

    @app.get("/")
    def chat_page() -> FileResponse:
        return FileResponse(_CHAT_PAGE_PATH, media_type="text/html")

    @app.get("/leads")
    def leads() -> list[dict[str, Any]]:
        return agent.lead_store.list_masked()

    @app.get("/health")
    def health() -> dict[str, str]:
        try:
            creds = get_llm_credentials()
            model = creds.model
        except RuntimeError:
            model = "unknown"
        return {"status": "ok", "model": model}

    return app
