"""
Agent router — dispatches a ClassificationResult to the correct agent.

Called synchronously (via asyncio.to_thread in main.py) because the
portfolio health agent does blocking yfinance I/O.
"""
import logging
from typing import Any, Dict

from src.agents.stubs import run_stub
from src.schemas import ClassificationResult

logger = logging.getLogger(__name__)


def route(classification: ClassificationResult, user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatch to the correct agent based on classification.agent.

    Returns a plain dict (the agent's result) — never raises.
    """
    agent = classification.agent
    entities = classification.entities

    # portfolio_query is a legacy alias used in conversation fixtures
    if agent in ("portfolio_health", "portfolio_query"):
        try:
            from src.agents.portfolio_health import run
            return run(user)
        except Exception as exc:
            logger.error("Portfolio health agent failed: %s", exc, exc_info=True)
            return run_stub("portfolio_health", entities, agent)

    return run_stub(agent, entities, agent)
