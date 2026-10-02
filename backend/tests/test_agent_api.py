from datetime import date

from fastapi.testclient import TestClient

from app.main import create_app
from app.api import agent as agent_api


def test_analysis_package_endpoint_forwards_topic(monkeypatch):
    calls: list[str | None] = []

    def fake_context(session, topic=None):
        calls.append(topic)
        return {"schema_version": "1.0", "topic": topic}

    monkeypatch.setattr(agent_api, "build_research_context", fake_context)
    response = TestClient(create_app()).get("/api/agent/analysis-package/today?topic=ETF")

    assert response.status_code == 200
    assert response.json() == {"schema_version": "1.0", "topic": "ETF"}
    assert calls == ["ETF"]


def test_append_review_endpoint_returns_write_result(monkeypatch):
    calls = []

    def fake_append(analysis_date, content, run_id=None):
        calls.append((analysis_date, content, run_id))
        return {"appended": True, "duplicate": False, "path": "review.md", "fingerprint": "abc"}

    monkeypatch.setattr(agent_api, "append_review_markdown", fake_append)
    response = TestClient(create_app()).post(
        "/api/agent/reviews/append",
        json={"analysis_date": "2026-08-31", "content": "## Review", "run_id": "run-1"},
    )

    assert response.status_code == 200
    assert response.json()["appended"] is True
    assert calls == [(date(2026, 8, 31), "## Review", "run-1")]


def test_append_review_endpoint_rejects_empty_content():
    response = TestClient(create_app()).post(
        "/api/agent/reviews/append",
        json={"analysis_date": "2026-08-31", "content": "   "},
    )

    assert response.status_code == 422
