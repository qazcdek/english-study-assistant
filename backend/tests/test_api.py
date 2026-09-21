import json

import pytest
from fastapi.testclient import TestClient

from app.deps import get_provider
from app.main import create_app
from tests.fake_provider import FakeProvider


@pytest.fixture
def make_client():
    def _make(provider: FakeProvider | None = None):
        app = create_app()
        app.dependency_overrides[get_provider] = lambda: provider or FakeProvider()
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client):
    with make_client() as c:
        yield c


def sse_events(response) -> list[dict]:
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm"]["reachable"] is True


def test_analyze(client):
    resp = client.post("/api/analyze", json={"text": "across the pond"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["result"]["overview"]["domain"] == "경제·금융 시사 논평"
    assert body["result"]["overview"]["key_expressions"] == ["across the pond"]
    assert body["markdown"]["full"].startswith("### 자연스러운 번역")
    assert body["meta"]["failed_parts"] == []


def test_blank_text_is_rejected(client):
    assert client.post("/api/analyze", json={"text": "   "}).status_code == 422


def test_stream_returns_sse_parts_then_done(client):
    resp = client.post("/api/analyze/stream", json={"text": "across the pond"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = sse_events(resp)
    assert [e["type"] for e in events] == ["part"] * 4 + ["done"]
    assert [e["field"] for e in events[:4]] == [
        "translation",
        "expressions",
        "structures",
        "overview",
    ]
    assert events[0]["markdown"].startswith("### 자연스러운 번역")
    assert events[-1]["meta"]["failed_parts"] == []


def test_stream_reports_a_failed_part_and_keeps_going(make_client):
    with make_client(FakeProvider({"structures": "깨진 응답"})) as client:
        events = sse_events(client.post("/api/analyze/stream", json={"text": "hi"}))

    assert [e["type"] for e in events] == ["part", "part", "part_error", "part", "done"]
    assert events[2]["field"] == "structures"
    assert events[2]["code"] == "llm_bad_output"
    assert events[-1]["meta"]["failed_parts"] == ["structures"]
    assert events[-1]["result"]["translation"]
