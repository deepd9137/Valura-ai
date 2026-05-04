"""
Classifier failure-mode tests.

Verifies that LLM errors, malformed JSON, and unknown agents all
fall back to general_query without raising exceptions.
No OPENAI_API_KEY required.
"""
import json
from unittest.mock import MagicMock

import pytest

from src.classifier import classify
from src.schemas import ClassificationResult


def _mock_returning(content: str) -> MagicMock:
    """Async mock that returns a fixed content string."""
    async def create(*args, **kwargs):
        resp = MagicMock()
        resp.choices[0].message.content = content
        return resp

    mock = MagicMock()
    mock.chat.completions.create = create
    return mock


def _mock_raising(exc: Exception) -> MagicMock:
    """Async mock that raises an exception."""
    async def create(*args, **kwargs):
        raise exc

    mock = MagicMock()
    mock.chat.completions.create = create
    return mock


# ---------------------------------------------------------------------------
# LLM exception fallbacks
# ---------------------------------------------------------------------------

async def test_fallback_on_api_error():
    from openai import APIConnectionError
    mock = _mock_raising(APIConnectionError(request=MagicMock()))
    result = await classify("hello", llm=mock)
    assert isinstance(result, ClassificationResult)
    assert result.agent == "general_query"


async def test_fallback_on_timeout():
    mock = _mock_raising(TimeoutError("timed out"))
    result = await classify("hello", llm=mock)
    assert result.agent == "general_query"


async def test_fallback_on_generic_exception():
    mock = _mock_raising(RuntimeError("unexpected"))
    result = await classify("hello", llm=mock)
    assert result.agent == "general_query"


# ---------------------------------------------------------------------------
# Malformed output fallbacks
# ---------------------------------------------------------------------------

async def test_fallback_on_non_json_response():
    mock = _mock_returning("Sorry, I can't help with that.")
    result = await classify("hello", llm=mock)
    assert result.agent == "general_query"


async def test_fallback_on_empty_response():
    mock = _mock_returning("")
    result = await classify("hello", llm=mock)
    assert result.agent == "general_query"


async def test_fallback_on_unknown_agent():
    payload = json.dumps({"agent": "made_up_agent", "entities": {}, "safety_verdict": "pass"})
    mock = _mock_returning(payload)
    result = await classify("hello", llm=mock)
    assert result.agent == "general_query"


async def test_fallback_never_raises():
    """classify() must never propagate an exception regardless of LLM behaviour."""
    mock = _mock_raising(Exception("anything"))
    try:
        result = await classify("some query", llm=mock)
        assert result.agent == "general_query"
    except Exception as exc:
        pytest.fail(f"classify() raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Happy path with valid response
# ---------------------------------------------------------------------------

async def test_valid_response_parsed_correctly():
    payload = json.dumps({
        "agent": "market_research",
        "entities": {"tickers": ["AAPL"]},
        "safety_verdict": "pass",
    })
    mock = _mock_returning(payload)
    result = await classify("what is the price of AAPL?", llm=mock)
    assert result.agent == "market_research"
    assert result.entities.get("tickers") == ["AAPL"]


async def test_entities_default_to_empty_dict_on_missing():
    payload = json.dumps({"agent": "general_query", "safety_verdict": "pass"})
    mock = _mock_returning(payload)
    result = await classify("hi", llm=mock)
    assert result.entities == {}


async def test_invalid_safety_verdict_normalised():
    payload = json.dumps({"agent": "general_query", "entities": {}, "safety_verdict": "invalid"})
    mock = _mock_returning(payload)
    result = await classify("hi", llm=mock)
    assert result.safety_verdict == "pass"
