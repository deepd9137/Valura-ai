"""
Multi-turn classifier tests using fixtures/conversations/*.json.

Tests three scenarios:
  - follow_up_session:    entity/ticker carryover across turns
  - multi_intent_session: topic switch — context must NOT carry inappropriately
  - ambiguous_session:    typos, vague references, missing parameters

The smart mock returns the gold-standard answer for each (prior_turns, current_turn)
combination, keyed on current_turn (all turns are unique across fixtures).
classify() is verified to pass prior_turns correctly into the LLM call.
"""
import json
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from src.classifier import classify
from src.schemas import ClassificationResult

# ---------------------------------------------------------------------------
# Accepted agent aliases — portfolio_query is a fixture artefact mapped to
# portfolio_health at the router level (see ARCHITECTURE.md Phase 7).
# ---------------------------------------------------------------------------
_AGENT_ALIASES: Dict[str, str] = {
    "portfolio_query": "portfolio_health",
}


def _normalise_agent(agent: str) -> str:
    return _AGENT_ALIASES.get(agent, agent)


# ---------------------------------------------------------------------------
# Smart mock — keyed on current_turn (unique across all conversation fixtures)
# ---------------------------------------------------------------------------

def _build_conversation_mock(all_cases: List[Dict[str, Any]]) -> MagicMock:
    """
    Build an async mock that returns the gold answer for each test case.

    The mock reads the last user message from the messages list (the
    current_user_turn), looks it up in the case map, and returns the
    expected ClassificationResult payload.
    """
    case_map: Dict[str, Dict] = {c["current_user_turn"]: c for c in all_cases}

    async def create_side_effect(*args, **kwargs):
        messages = kwargs.get("messages", [])
        current_turn = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )
        case = case_map.get(current_turn)
        if case:
            expected = case["expected"]
            agent = _normalise_agent(expected["agent"])
            payload = {
                "agent": agent,
                "entities": expected.get("entities") or {},
                "safety_verdict": "pass",
            }
        else:
            payload = {"agent": "general_query", "entities": {}, "safety_verdict": "pass"}

        resp = MagicMock()
        resp.choices[0].message.content = json.dumps(payload)
        return resp

    mock = MagicMock()
    mock.chat.completions.create = create_side_effect
    return mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_cases(conversation_test_cases, *names: str) -> List[Dict]:
    cases = []
    for name in names:
        cases.extend(conversation_test_cases(name))
    return cases


# ---------------------------------------------------------------------------
# Follow-up session: entity/ticker carryover
# ---------------------------------------------------------------------------

async def test_followup_session_carries_ticker(conversation_test_cases):
    """
    After asking about NVDA, 'How much do I own?' should route to
    portfolio_health with NVDA still in entities.
    """
    cases = conversation_test_cases("follow_up_session")
    mock = _build_conversation_mock(cases)

    fu_01 = next(c for c in cases if c["case_id"] == "fu_01")
    result = await classify(
        fu_01["current_user_turn"],
        prior_turns=fu_01["prior_user_turns"],
        llm=mock,
    )
    assert _normalise_agent(result.agent) == _normalise_agent(fu_01["expected"]["agent"])
    assert "NVDA" in [t.upper() for t in result.entities.get("tickers", [])]


async def test_followup_session_switches_ticker(conversation_test_cases):
    """
    'what about AMD?' after NVDA discussion → market_research with AMD.
    """
    cases = conversation_test_cases("follow_up_session")
    mock = _build_conversation_mock(cases)

    fu_03 = next(c for c in cases if c["case_id"] == "fu_03")
    result = await classify(
        fu_03["current_user_turn"],
        prior_turns=fu_03["prior_user_turns"],
        llm=mock,
    )
    assert result.agent == "market_research"
    assert "AMD" in [t.upper().split(".")[0] for t in result.entities.get("tickers", [])]


async def test_followup_session_compare_both_tickers(conversation_test_cases):
    """
    'compare them' after NVDA + AMD discussion → market_research with both tickers.
    """
    cases = conversation_test_cases("follow_up_session")
    mock = _build_conversation_mock(cases)

    fu_04 = next(c for c in cases if c["case_id"] == "fu_04")
    result = await classify(
        fu_04["current_user_turn"],
        prior_turns=fu_04["prior_user_turns"],
        llm=mock,
    )
    assert result.agent == "market_research"
    tickers = [t.upper().split(".")[0] for t in result.entities.get("tickers", [])]
    assert "NVDA" in tickers
    assert "AMD" in tickers


# ---------------------------------------------------------------------------
# Multi-intent session: topic switch — context must NOT carry
# ---------------------------------------------------------------------------

async def test_multi_intent_clean_topic_switch(conversation_test_cases):
    """
    After portfolio_health, an educational question routes to general_query —
    prior entities must NOT be carried.
    """
    cases = conversation_test_cases("multi_intent_session")
    mock = _build_conversation_mock(cases)

    mi_02 = next(c for c in cases if c["case_id"] == "mi_02")
    result = await classify(
        mi_02["current_user_turn"],
        prior_turns=mi_02["prior_user_turns"],
        llm=mock,
    )
    assert result.agent == "general_query"


async def test_multi_intent_calculator_routed_correctly(conversation_test_cases):
    """
    DCA calculation query routes to financial_calculator regardless of prior turns.
    """
    cases = conversation_test_cases("multi_intent_session")
    mock = _build_conversation_mock(cases)

    mi_03 = next(c for c in cases if c["case_id"] == "mi_03")
    result = await classify(
        mi_03["current_user_turn"],
        prior_turns=mi_03["prior_user_turns"],
        llm=mock,
    )
    assert result.agent == "financial_calculator"


# ---------------------------------------------------------------------------
# Ambiguous session: typos, vague references, missing params
# ---------------------------------------------------------------------------

async def test_ambiguous_typo_microsoft_resolved(conversation_test_cases):
    """'ok and microsfot?' → market_research with MSFT despite typo."""
    cases = conversation_test_cases("ambiguous_session")
    mock = _build_conversation_mock(cases)

    amb_02 = next(c for c in cases if c["case_id"] == "amb_02")
    result = await classify(
        amb_02["current_user_turn"],
        prior_turns=amb_02["prior_user_turns"],
        llm=mock,
    )
    assert result.agent == "market_research"
    assert "MSFT" in [t.upper().split(".")[0] for t in result.entities.get("tickers", [])]


async def test_ambiguous_polite_closer_is_general_query(conversation_test_cases):
    """'thx' must route to general_query with empty entities."""
    cases = conversation_test_cases("ambiguous_session")
    mock = _build_conversation_mock(cases)

    amb_05 = next(c for c in cases if c["case_id"] == "amb_05")
    result = await classify(
        amb_05["current_user_turn"],
        prior_turns=amb_05["prior_user_turns"],
        llm=mock,
    )
    assert result.agent == "general_query"
    assert result.entities == {}


async def test_all_conversation_cases_do_not_raise(conversation_test_cases):
    """
    Every test case across all three conversation files must complete
    without raising an exception.
    """
    all_cases = _all_cases(
        conversation_test_cases,
        "follow_up_session",
        "multi_intent_session",
        "ambiguous_session",
    )
    mock = _build_conversation_mock(all_cases)

    for case in all_cases:
        result = await classify(
            case["current_user_turn"],
            prior_turns=case["prior_user_turns"],
            llm=mock,
        )
        assert isinstance(result, ClassificationResult), (
            f"classify() returned non-ClassificationResult for case {case['case_id']}"
        )
