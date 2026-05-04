"""
Pure portfolio calculation functions.

No I/O, no LLM, no external calls — fully deterministic and unit-testable.
All monetary values are converted to base_currency before aggregation.
"""
from datetime import datetime
from typing import Dict, List, Optional

from src.schemas import BenchmarkComparison, ConcentrationRisk, Performance


def concentration(
    positions: List[Dict],
    prices: Dict[str, float],
    fx_rates: Dict[str, float],
) -> ConcentrationRisk:
    """
    Compute concentration risk for a set of positions.

    positions : list of {ticker, quantity, avg_cost, currency, ...}
    prices    : {ticker: current_price_in_position_currency}
    fx_rates  : {currency: rate_to_base_currency}

    Positions with missing prices are skipped (not included in total).
    Concentration flag thresholds:
        top position ≥ 40% → "high"
        top position 25–40% → "moderate"
        top position < 25%  → "low"
    """
    values: List[float] = []

    for pos in positions:
        ticker = pos["ticker"]
        price = prices.get(ticker)
        if price is None:
            continue
        fx = fx_rates.get(pos.get("currency", "USD"), 1.0)
        values.append(float(pos["quantity"]) * price * fx)

    if not values:
        return ConcentrationRisk(
            top_position_pct=0.0, top_3_positions_pct=0.0, flag="low"
        )

    total = sum(values)
    sorted_vals = sorted(values, reverse=True)

    top1_pct = round((sorted_vals[0] / total) * 100, 2)
    top3_pct = round((sum(sorted_vals[:3]) / total) * 100, 2)

    if top1_pct >= 40.0:
        flag = "high"
    elif top1_pct >= 25.0:
        flag = "moderate"
    else:
        flag = "low"

    return ConcentrationRisk(
        top_position_pct=top1_pct,
        top_3_positions_pct=top3_pct,
        flag=flag,
    )


def performance(
    positions: List[Dict],
    prices: Dict[str, float],
    fx_rates: Dict[str, float],
) -> Performance:
    """
    Compute total return and annualized return.

    Annualized return uses the earliest purchase date across all positions
    that have a current price. Returns None if holding period < ~5 weeks.
    """
    total_cost = 0.0
    total_current = 0.0
    purchase_dates: List[datetime] = []

    for pos in positions:
        ticker = pos["ticker"]
        price = prices.get(ticker)
        if price is None:
            continue
        fx = fx_rates.get(pos.get("currency", "USD"), 1.0)
        total_cost += float(pos["quantity"]) * float(pos["avg_cost"]) * fx
        total_current += float(pos["quantity"]) * price * fx

        purchased_at = pos.get("purchased_at")
        if purchased_at:
            try:
                purchase_dates.append(datetime.fromisoformat(str(purchased_at)))
            except ValueError:
                pass

    if total_cost == 0:
        return Performance(total_return_pct=0.0)

    total_return_pct = round(((total_current - total_cost) / total_cost) * 100, 2)

    annualized: Optional[float] = None
    if purchase_dates:
        earliest = min(purchase_dates)
        years = (datetime.now() - earliest).days / 365.25
        if years >= 0.1:  # at least ~5 weeks of history
            annualized = round(
                ((1 + total_return_pct / 100) ** (1 / years) - 1) * 100, 2
            )

    return Performance(
        total_return_pct=total_return_pct,
        annualized_return_pct=annualized,
    )


def benchmark_comparison(
    portfolio_return_pct: float,
    benchmark_return_pct: float,
    benchmark_name: str,
) -> BenchmarkComparison:
    """Compute alpha = portfolio_return - benchmark_return."""
    return BenchmarkComparison(
        benchmark=benchmark_name,
        portfolio_return_pct=round(portfolio_return_pct, 2),
        benchmark_return_pct=round(benchmark_return_pct, 2),
        alpha_pct=round(portfolio_return_pct - benchmark_return_pct, 2),
    )


def total_value(
    positions: List[Dict],
    prices: Dict[str, float],
    fx_rates: Dict[str, float],
) -> float:
    """Return total portfolio value in base currency."""
    total = 0.0
    for pos in positions:
        ticker = pos["ticker"]
        price = prices.get(ticker)
        if price is None:
            continue
        fx = fx_rates.get(pos.get("currency", "USD"), 1.0)
        total += float(pos["quantity"]) * price * fx
    return total
