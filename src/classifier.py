"""
Intent classifier — single LLM call per query.

Returns a ClassificationResult. Never raises: LLM failures fall back
to a safe general_query result so the pipeline always continues.
"""
import json
import logging
from typing import Any, List, Optional

from src.classifier_prompt import build_system_prompt
from src.schemas import AGENT_NAMES, ClassificationResult
from src.settings import Settings

logger = logging.getLogger(__name__)

_FALLBACK = ClassificationResult(agent="general_query", entities={}, safety_verdict="pass")
_settings = Settings()


async def classify(
    query: str,
    prior_turns: Optional[List[str]] = None,
    llm: Optional[Any] = None,
) -> ClassificationResult:
    """
    Classify a user query into one of the 10 agent intents.

    Args:
        query:       Current user message.
        prior_turns: Prior user messages in this session (oldest first).
                     Used to resolve follow-up references.
        llm:         AsyncOpenAI-compatible client. If None, one is created
                     from Settings. Injected for testability.

    Returns:
        ClassificationResult — never raises.
    """
    if prior_turns is None:
        prior_turns = []

    if llm is None:
        from openai import AsyncOpenAI
        llm = AsyncOpenAI(api_key=_settings.openai_api_key)

    system_prompt = build_system_prompt(prior_turns)

    try:
        response = await llm.chat.completions.create(
            model=_settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content
        return _parse(content)

    except Exception as exc:
        logger.warning("Classifier LLM call failed (%s: %s) — using fallback", type(exc).__name__, exc)
        return _FALLBACK


def _parse(content: str) -> ClassificationResult:
    """
    Parse LLM JSON output into ClassificationResult.

    Applies normalisation and falls back gracefully on any parse error.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Classifier returned non-JSON content — using fallback")
        return _FALLBACK

    # Normalise agent: unknown strings → general_query
    agent = data.get("agent", "general_query")
    if agent not in AGENT_NAMES:
        logger.warning("Classifier returned unknown agent %r — routing to general_query", agent)
        agent = "general_query"
    data["agent"] = agent

    # Ensure entities is always a dict
    if not isinstance(data.get("entities"), dict):
        data["entities"] = {}

    # Ensure safety_verdict is valid
    if data.get("safety_verdict") not in ("pass", "flag"):
        data["safety_verdict"] = "pass"

    try:
        return ClassificationResult.model_validate(data)
    except Exception as exc:
        logger.warning("ClassificationResult validation failed (%s) — using fallback", exc)
        return _FALLBACK
