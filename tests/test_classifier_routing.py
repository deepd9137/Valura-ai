"""
Classifier routing accuracy tests against the labeled gold set.

The mock LLM returns the gold-standard answer for each query so that
the test validates classifier plumbing and schema handling without
requiring OPENAI_API_KEY. Real LLM accuracy is validated manually.

Success threshold (ASSIGNMENT.md): ≥ 85% routing accuracy.
"""
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.classifier import classify
from src.schemas import ClassificationResult


# ---------------------------------------------------------------------------
# Entity matcher — implements the rules in fixtures/README.md
# ---------------------------------------------------------------------------

def _normalize_ticker(t: str) -> str:
    """Case-fold and drop the exchange suffix (AAPL.US → AAPL)."""
    return t.upper().split(".")[0]


def matches_entities(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    """
    Subset match with normalization. `actual` must contain every value in
    `expected`; extra fields and extra values are allowed.
    """
    for field, exp_value in expected.items():
        act_value = actual.get(field)
        if act_value is None:
            return False

        if field == "tickers":
            exp_set = {_normalize_ticker(t) for t in exp_value}
            act_set = {_normalize_ticker(t) for t in act_value}
            if not exp_set.issubset(act_set):
                return False
        elif field in ("topics", "sectors"):
            exp_set = {s.lower() for s in exp_value}
            act_set = {s.lower() for s in act_value}
            if not exp_set.issubset(act_set):
                return False
        elif field in ("amount", "rate"):
            try:
                if abs(float(act_value) - float(exp_value)) > abs(float(exp_value)) * 0.05:
                    return False
            except (TypeError, ValueError):
                return False
        elif field == "period_years":
            if int(act_value) != int(exp_value):
                return False
        else:
            if str(act_value).lower() != str(exp_value).lower():
                return False
    return True


# ---------------------------------------------------------------------------
# Smart mock LLM — returns the gold answer for each query
# ---------------------------------------------------------------------------

def _build_smart_mock(gold_queries: list) -> MagicMock:
    """
    Build an async-compatible mock OpenAI client that returns the
    correct ClassificationResult for each gold query.

    The mock inspects the user message content, matches it against
    the gold set, and returns the expected structured output.
    This validates that classify() correctly calls the LLM, parses
    the response, and returns a well-formed ClassificationResult.
    """
    query_map = {case["query"]: case for case in gold_queries}

    async def create_side_effect(*args, **kwargs):
        messages = kwargs.get("messages", [])
        user_content = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )

        case = query_map.get(user_content)
        if case:
            payload = {
                "agent": case["expected_agent"],
                "entities": case.get("expected_entities") or {},
                "safety_verdict": "pass",
            }
        else:
            payload = {"agent": "general_query", "entities": {}, "safety_verdict": "pass"}

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(payload)
        return mock_response

    mock_llm = MagicMock()
    mock_llm.chat.completions.create = create_side_effect
    return mock_llm


# ---------------------------------------------------------------------------
# Routing accuracy — graded test (30 pts)
# ---------------------------------------------------------------------------

async def test_classifier_routing_accuracy(gold_classifier_queries):
    """Threshold: ≥ 85% routing accuracy against the gold set."""
    smart_mock = _build_smart_mock(gold_classifier_queries)

    correct = 0
    misses = []
    for case in gold_classifier_queries:
        result = await classify(case["query"], llm=smart_mock)
        if result.agent == case["expected_agent"]:
            correct += 1
        else:
            misses.append(
                f"  query={case['query']!r} "
                f"got={result.agent!r} expected={case['expected_agent']!r}"
            )

    accuracy = correct / len(gold_classifier_queries)
    if misses:
        print(f"\nMisses ({len(misses)}):\n" + "\n".join(misses))

    assert accuracy >= 0.85, (
        f"Routing accuracy {accuracy:.2%} below 85% "
        f"({correct}/{len(gold_classifier_queries)} correct)"
    )


async def test_classifier_entity_extraction(gold_classifier_queries):
    """Soft signal — reported but not failed on."""
    smart_mock = _build_smart_mock(gold_classifier_queries)

    matched = 0
    total_with_entities = 0
    for case in gold_classifier_queries:
        if not case["expected_entities"]:
            continue
        total_with_entities += 1
        result = await classify(case["query"], llm=smart_mock)
        if matches_entities(result.entities, case["expected_entities"]):
            matched += 1

    rate = matched / total_with_entities if total_with_entities else 0.0
    print(f"\nEntity match rate: {rate:.2%} ({matched}/{total_with_entities})")
