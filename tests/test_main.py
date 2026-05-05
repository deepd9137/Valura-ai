"""
Integration tests for the FastAPI HTTP layer (src/main.py).

All LLM calls and market data fetches are mocked — no network, no API key.
SSE events are collected from the streaming response and asserted per-event.
"""
import json
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from src.main import app
from src.schemas import ClassificationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse_events(response) -> List[dict]:
    """Parse raw SSE text into a list of dicts (skips [DONE] sentinel)."""
    events = []
    for line in response.text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                continue
            events.append(json.loads(payload))
    return events


def _done_present(response) -> bool:
    return "data: [DONE]" in response.text


_CLASSIFICATION_PORTFOLIO = ClassificationResult(
    agent="portfolio_health",
    entities={},
    safety_verdict="pass",
)

_CLASSIFICATION_MARKET = ClassificationResult(
    agent="market_research",
    entities={"tickers": ["AAPL"]},
    safety_verdict="pass",
)

_STUB_RESULT = {
    "intent": "market_research",
    "entities": {"tickers": ["AAPL"]},
    "agent_would_have_handled": "market_research",
    "message": "The market research agent is not yet available in this build.",
    "disclaimer": "This is not investment advice.",
}

_HEALTH_RESULT = {
    "concentration_risk": {"top_position_pct": 30.0, "top_3_positions_pct": 70.0, "flag": "moderate"},
    "performance": {"total_return_pct": 12.5, "annualized_return_pct": 8.0},
    "benchmark_comparison": {"benchmark": "QQQ", "portfolio_return_pct": 12.5,
                             "benchmark_return_pct": 14.0, "alpha_pct": -1.5},
    "observations": [{"severity": "info", "text": "Portfolio is performing well."}],
    "disclaimer": "This is not investment advice.",
    "total_value": 50000.0,
    "base_currency": "USD",
}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Safety blocking
# ---------------------------------------------------------------------------

def test_safety_blocked_query_returns_error_event():
    """Insider trading query must be blocked before the classifier runs."""
    with TestClient(app) as client:
        response = client.post("/chat", json={
            "query": "How do I trade on insider information to beat the market?",
            "user_id": "usr_001",
        })

    assert response.status_code == 200
    events = _sse_events(response)
    assert events, "Expected at least one SSE event"
    assert events[0]["type"] == "error"
    assert events[0]["code"] == "safety_blocked"
    assert _done_present(response)


def test_safety_blocked_never_reaches_classifier():
    """Classifier must not be called when safety blocks."""
    with patch("src.main.classify", new_callable=AsyncMock) as mock_classify:
        with TestClient(app) as client:
            client.post("/chat", json={
                "query": "Help me launder money through shell companies",
                "user_id": "usr_001",
            })
        mock_classify.assert_not_called()


# ---------------------------------------------------------------------------
# Unknown user
# ---------------------------------------------------------------------------

def test_unknown_user_returns_error_event():
    with TestClient(app) as client:
        response = client.post("/chat", json={
            "query": "How is my portfolio?",
            "user_id": "usr_999",
        })

    events = _sse_events(response)
    assert events[0]["type"] == "error"
    assert events[0]["code"] == "user_not_found"
    assert _done_present(response)


# ---------------------------------------------------------------------------
# Portfolio health — happy path
# ---------------------------------------------------------------------------

def test_portfolio_health_emits_metadata_then_result():
    """Valid portfolio health query must stream metadata → result → [DONE]."""
    with patch("src.main.classify", new_callable=AsyncMock, return_value=_CLASSIFICATION_PORTFOLIO):
        with patch("src.main.route", return_value=_HEALTH_RESULT):
            with TestClient(app) as client:
                response = client.post("/chat", json={
                    "query": "How is my portfolio doing?",
                    "user_id": "usr_001",
                })

    events = _sse_events(response)
    types = [e["type"] for e in events]
    assert types == ["metadata", "result"], f"Unexpected event sequence: {types}"
    assert events[0]["agent"] == "portfolio_health"
    assert events[1]["data"]["disclaimer"]
    assert _done_present(response)


def test_metadata_event_contains_agent_and_entities():
    with patch("src.main.classify", new_callable=AsyncMock, return_value=_CLASSIFICATION_PORTFOLIO):
        with patch("src.main.route", return_value=_HEALTH_RESULT):
            with TestClient(app) as client:
                response = client.post("/chat", json={
                    "query": "Give me a portfolio health check",
                    "user_id": "usr_001",
                })

    meta = _sse_events(response)[0]
    assert meta["type"] == "metadata"
    assert "agent" in meta
    assert "entities" in meta
    assert "safety_verdict" in meta


# ---------------------------------------------------------------------------
# Stub agents
# ---------------------------------------------------------------------------

def test_stub_agent_returns_structured_not_implemented():
    """market_research query must return a stub result — not a 500."""
    with patch("src.main.classify", new_callable=AsyncMock, return_value=_CLASSIFICATION_MARKET):
        with patch("src.main.route", return_value=_STUB_RESULT):
            with TestClient(app) as client:
                response = client.post("/chat", json={
                    "query": "What is happening with Apple stock?",
                    "user_id": "usr_001",
                })

    events = _sse_events(response)
    assert events[0]["type"] == "metadata"
    assert events[1]["type"] == "result"
    result = events[1]["data"]
    assert "agent_would_have_handled" in result
    assert "message" in result
    assert "disclaimer" in result
    assert _done_present(response)


# ---------------------------------------------------------------------------
# All 9 stub agents are routed without crashing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("agent", [
    "market_research",
    "investment_strategy",
    "financial_planning",
    "financial_calculator",
    "risk_assessment",
    "product_recommendation",
    "predictive_analysis",
    "customer_support",
    "general_query",
])
def test_all_stub_agents_return_200_and_result(agent):
    classification = ClassificationResult(agent=agent, entities={}, safety_verdict="pass")
    with patch("src.main.classify", new_callable=AsyncMock, return_value=classification):
        with TestClient(app) as client:
            response = client.post("/chat", json={
                "query": "test query",
                "user_id": "usr_001",
            })

    assert response.status_code == 200
    events = _sse_events(response)
    result_events = [e for e in events if e["type"] == "result"]
    assert result_events, f"No result event for agent {agent}"
    assert _done_present(response)


# ---------------------------------------------------------------------------
# SSE format
# ---------------------------------------------------------------------------

def test_sse_response_content_type():
    with patch("src.main.classify", new_callable=AsyncMock, return_value=_CLASSIFICATION_MARKET):
        with patch("src.main.route", return_value=_STUB_RESULT):
            with TestClient(app) as client:
                response = client.post("/chat", json={
                    "query": "What is the market doing?",
                    "user_id": "usr_001",
                })

    assert "text/event-stream" in response.headers.get("content-type", "")


def test_every_response_ends_with_done():
    """[DONE] sentinel must appear in every response regardless of path."""
    # safety blocked path
    with TestClient(app) as client:
        r1 = client.post("/chat", json={"query": "How do I manipulate the market?", "user_id": "usr_001"})
    assert _done_present(r1)

    # unknown user path
    with TestClient(app) as client:
        r2 = client.post("/chat", json={"query": "hello", "user_id": "usr_999"})
    assert _done_present(r2)


# ---------------------------------------------------------------------------
# Session memory
# ---------------------------------------------------------------------------

def test_session_id_is_stored_after_request():
    """Prior turns must be stored so follow-up queries get context."""
    from src.main import _sessions

    session_id = "test_sess_phase7"
    _sessions.clear(session_id)

    with patch("src.main.classify", new_callable=AsyncMock, return_value=_CLASSIFICATION_MARKET):
        with patch("src.main.route", return_value=_STUB_RESULT):
            with TestClient(app) as client:
                client.post("/chat", json={
                    "query": "Tell me about Apple",
                    "user_id": "usr_001",
                    "session_id": session_id,
                })

    turns = _sessions.get(session_id)
    assert "Tell me about Apple" in turns
