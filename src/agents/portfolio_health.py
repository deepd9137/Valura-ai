"""
Portfolio Health Agent.

Receives a user profile dict, fetches live market data, computes
concentration / performance / benchmark metrics using portfolio_math,
generates rule-based observations, and returns a PortfolioHealthResult dict.

All external I/O (MarketData) is injectable so tests can run fully offline.
"""
import logging
from typing import Any, Dict, List, Optional

from src.agents.portfolio_math import (
    benchmark_comparison,
    concentration,
    performance,
    total_value,
)
from src.schemas import BenchmarkComparison, ConcentrationRisk, Observation, Performance

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "This analysis is for informational purposes only and is not investment advice. "
    "Past performance is not indicative of future results. "
    "Always consult a qualified financial adviser before making investment decisions."
)

_BUILD_OBSERVATIONS: List[Dict] = [
    {
        "severity": "info",
        "text": (
            "Your portfolio is empty — now is a great time to start building. "
            "Consider a low-cost diversified ETF (e.g. VTI for US equities, "
            "VXUS for international) as a first position."
        ),
    },
    {
        "severity": "info",
        "text": (
            "With a moderate risk profile, a common starting framework is "
            "60% equities / 40% bonds. Adjust based on your time horizon "
            "and how much short-term volatility you can stomach."
        ),
    },
    {
        "severity": "info",
        "text": (
            "Start with broad market exposure before adding individual stocks. "
            "Dollar-cost averaging (investing a fixed amount regularly) reduces "
            "the risk of buying at a peak."
        ),
    },
]


def run(
    user: Dict[str, Any],
    llm: Any = None,  # reserved for future narrative enhancement; unused in current impl
    market_data: Any = None,
) -> Dict[str, Any]:
    """
    Run a portfolio health check for a user.

    Args:
        user:        User profile dict (from fixtures/users/).
        llm:         Optional LLM client — reserved for future narrative generation.
        market_data: Optional MarketData instance. If None, a real one is created.
                     Inject a mock for tests.

    Returns:
        Dict matching PortfolioHealthResult schema.
    """
    positions = user.get("positions", [])
    base_currency = user.get("base_currency", "USD")
    preferred_benchmark = (
        user.get("preferences", {}).get("preferred_benchmark") or "S&P 500"
    )

    if not positions:
        return _empty_portfolio_response(preferred_benchmark)

    if market_data is None:
        from src.market_data import MarketData  # lazy import to keep tests fast
        market_data = MarketData()

    tickers = [p["ticker"] for p in positions]
    prices = market_data.get_prices(tickers)

    currencies = list({p.get("currency", base_currency) for p in positions})
    fx_rates = market_data.get_fx_rates(currencies, base=base_currency)
    # Ensure base currency always maps to 1.0
    fx_rates.setdefault(base_currency, 1.0)

    benchmark_return_pct = market_data.get_benchmark_return(preferred_benchmark)

    conc: ConcentrationRisk = concentration(positions, prices, fx_rates)
    perf: Performance = performance(positions, prices, fx_rates)
    bench: BenchmarkComparison = benchmark_comparison(
        perf.total_return_pct, benchmark_return_pct, preferred_benchmark
    )

    portfolio_total = total_value(positions, prices, fx_rates)
    observations = _generate_observations(
        conc, perf, bench, positions, prices, portfolio_total
    )

    return {
        "concentration_risk": conc.model_dump(),
        "performance": perf.model_dump(),
        "benchmark_comparison": bench.model_dump(),
        "observations": [o.model_dump() for o in observations],
        "disclaimer": DISCLAIMER,
        "total_value": round(portfolio_total, 2),
        "base_currency": base_currency,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_portfolio_response(preferred_benchmark: str) -> Dict[str, Any]:
    return {
        "concentration_risk": ConcentrationRisk(
            top_position_pct=0.0, top_3_positions_pct=0.0, flag="low"
        ).model_dump(),
        "performance": Performance(
            total_return_pct=0.0, annualized_return_pct=None
        ).model_dump(),
        "benchmark_comparison": BenchmarkComparison(
            benchmark=preferred_benchmark,
            portfolio_return_pct=0.0,
            benchmark_return_pct=0.0,
            alpha_pct=0.0,
        ).model_dump(),
        "observations": _BUILD_OBSERVATIONS,
        "disclaimer": DISCLAIMER,
        "total_value": 0.0,
        "base_currency": "USD",
    }


def _generate_observations(
    conc: ConcentrationRisk,
    perf: Performance,
    bench: BenchmarkComparison,
    positions: List[Dict],
    prices: Dict[str, float],
    portfolio_total: float,
) -> List[Observation]:
    obs: List[Observation] = []

    # --- Concentration ---
    if conc.flag == "high":
        top_pos = _top_position(positions, prices)
        obs.append(
            Observation(
                severity="warning",
                text=(
                    f"{top_pos} makes up {conc.top_position_pct:.1f}% of your portfolio. "
                    "This level of concentration means one bad earnings report could "
                    "significantly hurt your overall returns."
                ),
            )
        )
    elif conc.flag == "moderate":
        top_pos = _top_position(positions, prices)
        obs.append(
            Observation(
                severity="info",
                text=(
                    f"Your largest position ({top_pos}) is {conc.top_position_pct:.1f}% "
                    "of the portfolio — moderate concentration. Consider whether you're "
                    "comfortable with this exposure."
                ),
            )
        )

    # --- Performance vs benchmark ---
    if bench.alpha_pct > 5.0:
        obs.append(
            Observation(
                severity="info",
                text=(
                    f"You're outperforming {bench.benchmark} by {bench.alpha_pct:.1f}% "
                    f"({bench.portfolio_return_pct:.1f}% vs {bench.benchmark_return_pct:.1f}%). "
                    "Strong result — keep monitoring whether the concentration driving this "
                    "is within your risk tolerance."
                ),
            )
        )
    elif bench.alpha_pct < -5.0:
        obs.append(
            Observation(
                severity="warning",
                text=(
                    f"You're underperforming {bench.benchmark} by {abs(bench.alpha_pct):.1f}% "
                    f"({bench.portfolio_return_pct:.1f}% vs {bench.benchmark_return_pct:.1f}%). "
                    "It may be worth reviewing whether active stock picks are adding value "
                    "compared to a passive index fund."
                ),
            )
        )
    else:
        obs.append(
            Observation(
                severity="info",
                text=(
                    f"Performance is broadly in line with {bench.benchmark} "
                    f"({bench.portfolio_return_pct:.1f}% portfolio vs "
                    f"{bench.benchmark_return_pct:.1f}% benchmark)."
                ),
            )
        )

    # --- Annualized return ---
    if perf.annualized_return_pct is not None:
        if perf.annualized_return_pct > 15.0:
            obs.append(
                Observation(
                    severity="info",
                    text=(
                        f"Annualized return of {perf.annualized_return_pct:.1f}% is strong. "
                        "Bear in mind that recent bull markets may not persist — "
                        "ensure your position sizes reflect a potential downturn."
                    ),
                )
            )
        elif perf.annualized_return_pct < 0:
            obs.append(
                Observation(
                    severity="warning",
                    text=(
                        f"Annualized return is negative ({perf.annualized_return_pct:.1f}%). "
                        "Review whether your holdings align with your investment thesis "
                        "or if rebalancing makes sense."
                    ),
                )
            )

    # --- Diversification: very few positions ---
    priced_positions = [p for p in positions if p["ticker"] in prices]
    if 0 < len(priced_positions) <= 2:
        obs.append(
            Observation(
                severity="warning",
                text=(
                    f"You hold only {len(priced_positions)} position(s). "
                    "Adding uncorrelated assets (e.g. bonds, international equities) "
                    "can reduce volatility without sacrificing long-term returns."
                ),
            )
        )

    return obs


def _top_position(positions: List[Dict], prices: Dict[str, float]) -> str:
    """Return the ticker of the highest-value position with a known price."""
    best_ticker = ""
    best_value = -1.0
    for pos in positions:
        price = prices.get(pos["ticker"])
        if price is None:
            continue
        val = float(pos["quantity"]) * price
        if val > best_value:
            best_value = val
            best_ticker = pos["ticker"]
    return best_ticker or "your top holding"
