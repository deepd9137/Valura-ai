"""
Round-trip serialization tests for all shared Pydantic models.
No LLM calls — pure schema validation.
"""
import json

import pytest
from pydantic import ValidationError

from src.schemas import (
    AGENT_NAMES,
    BenchmarkComparison,
    ChatRequest,
    ChatResponseEvent,
    ClassificationResult,
    ConcentrationRisk,
    Observation,
    Performance,
    PortfolioHealthResult,
    SafetyVerdict,
    StubAgentResult,
)


# ---------------------------------------------------------------------------
# SafetyVerdict
# ---------------------------------------------------------------------------

def test_safety_verdict_blocked():
    v = SafetyVerdict(blocked=True, category="insider_trading", message="Cannot help.")
    assert v.blocked is True
    assert v.category == "insider_trading"


def test_safety_verdict_pass():
    v = SafetyVerdict(blocked=False)
    assert v.category is None
    assert v.message is None


# ---------------------------------------------------------------------------
# ChatRequest
# ---------------------------------------------------------------------------

def test_chat_request_requires_query_and_user_id():
    r = ChatRequest(query="how is my portfolio?", user_id="usr_001")
    assert r.session_id is None


def test_chat_request_missing_user_id_raises():
    with pytest.raises(ValidationError):
        ChatRequest(query="hello")


def test_chat_request_with_session_id():
    r = ChatRequest(query="hi", user_id="usr_001", session_id="sess_abc")
    assert r.session_id == "sess_abc"


# ---------------------------------------------------------------------------
# ClassificationResult
# ---------------------------------------------------------------------------

def test_classification_result_round_trip():
    cr = ClassificationResult(
        agent="portfolio_health",
        entities={"tickers": ["AAPL"]},
        safety_verdict="pass",
    )
    serialized = cr.model_dump_json()
    restored = ClassificationResult.model_validate_json(serialized)
    assert restored == cr


def test_classification_result_defaults():
    cr = ClassificationResult(agent="general_query")
    assert cr.entities == {}
    assert cr.safety_verdict == "pass"


def test_classification_result_rejects_unknown_agent():
    with pytest.raises(ValidationError):
        ClassificationResult(agent="unknown_agent")


def test_classification_result_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ClassificationResult(agent="market_research", unknown_field="oops")


def test_classification_result_all_10_agents_valid():
    for name in AGENT_NAMES:
        cr = ClassificationResult(agent=name)
        assert cr.agent == name


def test_classification_result_json_schema_has_agent_enum():
    schema = ClassificationResult.model_json_schema()
    # agent field should enumerate all valid agent strings
    agent_def = schema["properties"]["agent"]
    # Pydantic v2 may nest the enum inside $defs or inline it
    if "enum" in agent_def:
        enums = agent_def["enum"]
    else:
        # follow $ref
        ref = agent_def.get("$ref", "")
        def_key = ref.split("/")[-1]
        enums = schema["$defs"][def_key]["enum"]
    assert set(enums) == set(AGENT_NAMES)


def test_classification_result_json_schema_has_required():
    schema = ClassificationResult.model_json_schema()
    assert "agent" in schema.get("required", [])


# ---------------------------------------------------------------------------
# PortfolioHealthResult
# ---------------------------------------------------------------------------

def _make_portfolio_result() -> PortfolioHealthResult:
    return PortfolioHealthResult(
        concentration_risk=ConcentrationRisk(
            top_position_pct=60.4,
            top_3_positions_pct=78.2,
            flag="high",
        ),
        performance=Performance(total_return_pct=18.4, annualized_return_pct=12.1),
        benchmark_comparison=BenchmarkComparison(
            benchmark="S&P 500",
            portfolio_return_pct=18.4,
            benchmark_return_pct=14.2,
            alpha_pct=4.2,
        ),
        observations=[
            Observation(severity="warning", text="60% in NVDA — highly concentrated."),
            Observation(severity="info", text="Outperforming S&P 500 by 4.2%."),
        ],
        disclaimer="This is not investment advice.",
    )


def test_portfolio_health_result_round_trip():
    result = _make_portfolio_result()
    serialized = result.model_dump_json()
    restored = PortfolioHealthResult.model_validate_json(serialized)
    assert restored == result


def test_portfolio_health_disclaimer_present():
    result = _make_portfolio_result()
    assert "not investment advice" in result.disclaimer.lower()


def test_portfolio_health_concentration_flag_values():
    for flag in ("low", "moderate", "high"):
        c = ConcentrationRisk(top_position_pct=10.0, top_3_positions_pct=20.0, flag=flag)
        assert c.flag == flag


def test_portfolio_health_rejects_invalid_flag():
    with pytest.raises(ValidationError):
        ConcentrationRisk(top_position_pct=10.0, top_3_positions_pct=20.0, flag="extreme")


def test_observation_severity_values():
    for sev in ("info", "warning", "critical"):
        o = Observation(severity=sev, text="test")
        assert o.severity == sev


def test_portfolio_health_annualized_return_optional():
    p = Performance(total_return_pct=10.0)
    assert p.annualized_return_pct is None


# ---------------------------------------------------------------------------
# StubAgentResult
# ---------------------------------------------------------------------------

def test_stub_agent_result_round_trip():
    stub = StubAgentResult(
        intent="market_research",
        entities={"tickers": ["TSLA"]},
        agent_would_have_handled="market_research",
        message="Agent not implemented in this build.",
        disclaimer="This is not investment advice.",
    )
    assert stub.model_dump_json()


# ---------------------------------------------------------------------------
# ChatResponseEvent
# ---------------------------------------------------------------------------

def test_chat_response_event_metadata():
    e = ChatResponseEvent(
        type="metadata",
        agent="portfolio_health",
        entities={},
        safety_verdict="pass",
    )
    assert e.type == "metadata"


def test_chat_response_event_error():
    e = ChatResponseEvent(type="error", code="safety_blocked", message="Cannot help.")
    assert e.code == "safety_blocked"
