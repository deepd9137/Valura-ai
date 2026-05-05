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

    if agent == "portfolio_health":
        try:
            from src.agents.portfolio_health import run
            return run(user)
        except Exception as exc:
            logger.error("Portfolio health agent failed: %s", exc, exc_info=True)
            return run_stub(agent, entities, agent)

    return run_stub(agent, entities, agent)
