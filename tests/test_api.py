import dataclasses
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from meher_agent.agent import Agent
from meher_agent.api import create_app
from meher_agent.config import load_settings
from meher_agent.knowledge import load_knowledge_base
from meher_agent.llm import LLMResponse, ToolCall

BASE_SETTINGS = load_settings()
TEST_SETTINGS = dataclasses.replace(
    BASE_SETTINGS, server=dataclasses.replace(BASE_SETTINGS.server, warmup_on_start=False)
)
KB = load_knowledge_base(TEST_SETTINGS)


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def chat(self, messages, tools):
        if not self.responses:
            raise AssertionError("FakeLLM ran out of scripted responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def text_response(content):
    return LLMResponse(content=content, tool_calls=[], prompt_tokens=10, completion_tokens=5)


def tool_response(name, arguments, call_id="call-1"):
    return LLMResponse(
        content="",
        tool_calls=[ToolCall(id=call_id, name=name, arguments=json.dumps(arguments))],
        prompt_tokens=10,
        completion_tokens=5,
    )


def make_client(responses):
    agent = Agent(llm=FakeLLM(responses), kb=KB, settings=TEST_SETTINGS)
    app = create_app(settings=TEST_SETTINGS, agent=agent)
    return TestClient(app)


# ---------------------------------------------------------------------------
# /chat basic shape
# ---------------------------------------------------------------------------


def test_chat_response_shape():
    with make_client([text_response("We are open every day, 9 am to 10 pm.")]) as client:
        resp = client.post("/chat", json={"conversation_id": "conv-1", "message": "hours?"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"reply", "sources", "actions", "handoff", "usage"}
    assert isinstance(body["reply"], str)
    assert isinstance(body["sources"], list)
    assert isinstance(body["actions"], list)
    assert isinstance(body["handoff"], bool)
    assert set(body["usage"].keys()) == {
        "prompt_tokens",
        "completion_tokens",
        "model_calls",
        "latency_ms",
        "estimated",
    }


# ---------------------------------------------------------------------------
# Disclosure and history
# ---------------------------------------------------------------------------


def test_disclosure_only_on_first_message_same_conversation():
    with make_client([text_response("We are open 9 to 10."), text_response("Yes, we deliver.")]) as client:
        r1 = client.post("/chat", json={"conversation_id": "conv-1", "message": "hours?"})
        r2 = client.post("/chat", json={"conversation_id": "conv-1", "message": "delivery?"})
    assert "AI assistant" in r1.json()["reply"]
    assert "AI assistant" not in r2.json()["reply"]


def test_different_conversation_ids_independent():
    with make_client([text_response("Reply A"), text_response("Reply B")]) as client:
        r1 = client.post("/chat", json={"conversation_id": "conv-a", "message": "hello"})
        r2 = client.post("/chat", json={"conversation_id": "conv-b", "message": "hello"})
    assert "AI assistant" in r1.json()["reply"]
    assert "AI assistant" in r2.json()["reply"]  # both are first messages in their own conversation


# ---------------------------------------------------------------------------
# /leads
# ---------------------------------------------------------------------------


def test_leads_endpoint_masks_contact_details():
    with make_client(
        [
            tool_response(
                "save_lead",
                {"name": "Ritu Malhotra", "need": "gift boxes", "email": "ritu.m@example.com", "phone": "9876543210"},
            ),
            text_response("Thanks, the team will follow up by email."),
        ]
    ) as client:
        client.post("/chat", json={"conversation_id": "conv-1", "message": "save my details"})
        resp = client.get("/leads")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["email"] == "r*****@example.com"
    assert body[0]["phone"] == "******3210"
    raw_body = resp.text
    assert "ritu.m@example.com" not in raw_body
    assert "9876543210" not in raw_body


# ---------------------------------------------------------------------------
# Escalate -> handoff
# ---------------------------------------------------------------------------


def test_escalate_sets_handoff_true():
    with make_client(
        [
            tool_response("escalate", {"reason": "damaged delivery"}),
            text_response("I'm sorry to hear that. The team will follow up by email."),
        ]
    ) as client:
        resp = client.post("/chat", json={"conversation_id": "conv-1", "message": "my order is damaged"})
    assert resp.json()["handoff"] is True


# ---------------------------------------------------------------------------
# Validation errors -> 422
# ---------------------------------------------------------------------------


def test_empty_message_422():
    with make_client([]) as client:
        resp = client.post("/chat", json={"conversation_id": "conv-1", "message": ""})
    assert resp.status_code == 422


def test_missing_conversation_id_422():
    with make_client([]) as client:
        resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 422


def test_message_too_long_422():
    with make_client([]) as client:
        resp = client.post("/chat", json={"conversation_id": "conv-1", "message": "x" * 5000})
    assert resp.status_code == 422


def test_invalid_conversation_id_characters_422():
    with make_client([]) as client:
        resp = client.post("/chat", json={"conversation_id": "has spaces!", "message": "hello"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_endpoint():
    with make_client([]) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "model" in body


# ---------------------------------------------------------------------------
# Logging never leaks contact details
# ---------------------------------------------------------------------------


def test_logs_never_contain_raw_contact_details(caplog):
    with make_client([text_response("Noted, thank you.")]) as client:
        with caplog.at_level(logging.INFO):
            client.post(
                "/chat",
                json={
                    "conversation_id": "conv-1",
                    "message": "My number is +91 98765 43210 and email ritu.m@example.com",
                },
            )
    log_text = caplog.text
    assert "98765" not in log_text
    assert "43210" not in log_text
    assert "ritu.m@example.com" not in log_text
