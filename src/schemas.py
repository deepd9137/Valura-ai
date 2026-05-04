"""
Shared Pydantic models for Valura AI.

All request/response boundaries, agent outputs, and inter-component
contracts are defined here. Python 3.9 compatible (uses typing module).
"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

class SafetyVerdict(BaseModel):
    blocked: bool
    category: Optional[str] = None
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    query: str
    user_id: str
    session_id: Optional[str] = None


class ChatResponseEvent(BaseModel):
    """One SSE frame emitted by the pipeline."""
    type: Literal["metadata", "result", "error", "chunk"]
    # Only one of these will be populated per event type
    agent: Optional[str] = None
    entities: Optional[Dict[str, Any]] = None
    safety_verdict: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    content: Optional[str] = None
    code: Optional[str] = None
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Intent classifier
# ---------------------------------------------------------------------------

AGENT_TAXONOMY = Literal[
    "portfolio_health",
    "market_research",
    "investment_strategy",
    "financial_planning",
    "financial_calculator",
    "risk_assessment",
    "product_recommendation",
    "predictive_analysis",
    "customer_support",
    "general_query",
]

AGENT_NAMES: List[str] = [
    "portfolio_health",
    "market_research",
    "investment_strategy",
    "financial_planning",
    "financial_calculator",
    "risk_assessment",
    "product_recommendation",
    "predictive_analysis",
    "customer_support",
    "general_query",
]


class ClassificationResult(BaseModel):
    """
    Structured output from the intent classifier (single LLM call).

    `safety_verdict` is informational only — it does not re-block a query.
    The SafetyGuard is the sole authority for blocking.
    """
    model_config = ConfigDict(extra="forbid")

    agent: AGENT_TAXONOMY
    entities: Dict[str, Any] = Field(default_factory=dict)
    safety_verdict: Literal["pass", "flag"] = "pass"


# ---------------------------------------------------------------------------
# Portfolio Health agent output
# ---------------------------------------------------------------------------

class Observation(BaseModel):
    severity: Literal["info", "warning", "critical"]
    text: str


class ConcentrationRisk(BaseModel):
    top_position_pct: float
    top_3_positions_pct: float
    flag: Literal["low", "moderate", "high"]


class Performance(BaseModel):
    total_return_pct: float
    annualized_return_pct: Optional[float] = None


class BenchmarkComparison(BaseModel):
    benchmark: str
    portfolio_return_pct: float
    benchmark_return_pct: float
    alpha_pct: float


class PortfolioHealthResult(BaseModel):
    concentration_risk: ConcentrationRisk
    performance: Performance
    benchmark_comparison: BenchmarkComparison
    observations: List[Observation]
    disclaimer: str


# ---------------------------------------------------------------------------
# Stub agent output (for the 9 unimplemented agents)
# ---------------------------------------------------------------------------

class StubAgentResult(BaseModel):
    intent: str
    entities: Dict[str, Any]
    agent_would_have_handled: str
    message: str
    disclaimer: str
