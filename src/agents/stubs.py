"""
Stub handlers for the 9 unimplemented specialist agents.

Every stub returns a structured dict that matches StubAgentResult so the
pipeline always has something to stream — no 500s, no crashes.
"""
from typing import Any, Dict

STUB_DISCLAIMER = (
    "This is not investment advice. Valura AI is a demonstration system. "
    "Always consult a qualified financial adviser before making investment decisions."
)

_AGENT_DESCRIPTIONS: Dict[str, str] = {
    "market_research": "real-time market data, news sentiment, and fundamental analysis",
    "investment_strategy": "portfolio construction, asset allocation, and rebalancing strategies",
    "financial_planning": "goal-based planning, retirement projections, and savings targets",
    "financial_calculator": "compound interest, loan amortisation, and return calculations",
    "risk_assessment": "volatility analysis, drawdown scenarios, and stress testing",
    "product_recommendation": "instrument selection aligned to risk profile and goals",
    "predictive_analysis": "price forecasting, trend analysis, and scenario modelling",
    "customer_support": "account queries, platform help, and general assistance",
    "general_query": "general financial questions and educational content",
}


def run_stub(agent: str, entities: Dict[str, Any], intent: str) -> Dict[str, Any]:
    """
    Return a structured not-implemented payload for any non-portfolio-health agent.

    Args:
        agent:    The agent name from the classifier (e.g. "market_research").
        entities: Extracted entities from the classifier.
        intent:   The classified intent string (same as agent in current taxonomy).

    Returns:
        Dict matching StubAgentResult schema.
    """
    description = _AGENT_DESCRIPTIONS.get(agent, "specialised financial analysis")
    return {
        "intent": intent,
        "entities": entities,
        "agent_would_have_handled": agent,
        "message": (
            f"The {agent.replace('_', ' ')} agent ({description}) "
            "is not yet available in this build. Your query has been "
            "classified and routed correctly — the agent will be implemented "
            "in a future release."
        ),
        "disclaimer": STUB_DISCLAIMER,
    }
