import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from meher_agent.agent import Agent
from meher_agent.api import create_app
from meher_agent.config import load_settings
from meher_agent.knowledge import load_knowledge_base

BASE_SETTINGS = load_settings()
TEST_SETTINGS = dataclasses.replace(
    BASE_SETTINGS, server=dataclasses.replace(BASE_SETTINGS.server, warmup_on_start=False)
)
KB = load_knowledge_base(TEST_SETTINGS)

CHAT_HTML_PATH = Path(__file__).resolve().parents[1] / "src" / "meher_agent" / "static" / "chat.html"


class FakeLLM:
    def chat(self, messages, tools):
        raise AssertionError("this test never expects the agent to be called")


def make_client():
    agent = Agent(llm=FakeLLM(), kb=KB, settings=TEST_SETTINGS)
    app = create_app(settings=TEST_SETTINGS, agent=agent)
    return TestClient(app)


def test_root_serves_chat_page():
    with make_client() as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert 'id="messageInput"' in body
    assert 'id="sendBtn"' in body
    assert "/chat" in body


def test_chat_html_never_uses_innerHTML():
    html = CHAT_HTML_PATH.read_text(encoding="utf-8")
    assert "innerHTML" not in html


def test_chat_html_uses_textcontent_or_createtextnode_for_dom_updates():
    html = CHAT_HTML_PATH.read_text(encoding="utf-8")
    assert "textContent" in html or "createTextNode" in html
