"""
Pure unit tests for portfolio_math functions.
No mocks, no network, no LLM — deterministic math only.
"""
import pytest

from src.agents.portfolio_math import (
    benchmark_comparison,
    concentration,
    performance,
    total_value,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pos(ticker, qty, avg_cost, currency="USD", purchased_at="2023-01-01"):
    return {
        "ticker": ticker,
        "quantity": qty,
        "avg_cost": avg_cost,
        "currency": currency,
        "purchased_at": purchased_at,
    }


USD = {"USD": 1.0}
USD_EUR = {"USD": 1.0, "EUR": 1.08}


# ---------------------------------------------------------------------------
# concentration()
# ---------------------------------------------------------------------------

def test_concentration_empty_positions():
    result = concentration([], {}, USD)
    assert result.top_position_pct == 0.0
    assert result.top_3_positions_pct == 0.0
    assert result.flag == "low"


def test_concentration_single_position_is_100_pct():
    pos = [_pos("AAPL", 10, 100.0)]
    result = concentration(pos, {"AAPL": 150.0}, USD)
    assert result.top_position_pct == 100.0
    assert result.top_3_positions_pct == 100.0
    assert result.flag == "high"


def test_concentration_flag_high_above_40_pct():
    positions = [
        _pos("NVDA", 180, 218.0),   # 180 * 600 = 108_000 (~60%)
        _pos("VTI", 25, 218.0),     # 25  * 230 = 5_750
        _pos("AAPL", 8, 168.0),     # 8   * 180 = 1_440
    ]
    prices = {"NVDA": 600.0, "VTI": 230.0, "AAPL": 180.0}
    result = concentration(positions, prices, USD)
    assert result.flag == "high"
    assert result.top_position_pct > 40.0


def test_concentration_flag_moderate_25_to_40_pct():
    positions = [
        _pos("A", 1, 100.0),  # 30%
        _pos("B", 1, 100.0),  # 30%
        _pos("C", 1, 100.0),  # 20%  (but 30% is highest)
    ]
    # equal weights → 33% each → "moderate"
    prices = {"A": 100.0, "B": 100.0, "C": 100.0}
    result = concentration(positions, prices, USD)
    assert result.flag == "moderate"
    assert 25.0 <= result.top_position_pct <= 40.0


def test_concentration_flag_low_below_25_pct():
    positions = [_pos(str(i), 1, 100.0) for i in range(5)]
    prices = {str(i): 100.0 for i in range(5)}
    result = concentration(positions, prices, USD)
    assert result.flag == "low"
    assert result.top_position_pct == 20.0


def test_concentration_skips_missing_price():
    positions = [_pos("AAPL", 10, 100.0), _pos("GHOST", 10, 100.0)]
    result = concentration(positions, {"AAPL": 150.0}, USD)
    # GHOST not in prices — only AAPL counts
    assert result.top_position_pct == 100.0


def test_concentration_multi_currency():
    positions = [
        _pos("ASML", 5, 700.0, currency="EUR"),
        _pos("AAPL", 10, 150.0, currency="USD"),
    ]
    prices = {"ASML": 800.0, "AAPL": 160.0}
    # ASML in EUR: 5 * 800 * 1.08 = 4_320
    # AAPL in USD: 10 * 160 * 1.0 = 1_600
    result = concentration(positions, prices, USD_EUR)
    assert result.flag == "high"
    assert result.top_position_pct > 40.0


def test_concentration_top3_capped_at_total():
    positions = [_pos(str(i), 1, 100.0) for i in range(2)]
    prices = {str(i): 100.0 for i in range(2)}
    result = concentration(positions, prices, USD)
    # only 2 positions — top_3 == top_1 + top_2 == 100%
    assert result.top_3_positions_pct == 100.0


# ---------------------------------------------------------------------------
# performance()
# ---------------------------------------------------------------------------

def test_performance_empty_returns_zero():
    result = performance([], {}, USD)
    assert result.total_return_pct == 0.0
    assert result.annualized_return_pct is None


def test_performance_positive_return():
    pos = [_pos("AAPL", 10, 100.0, purchased_at="2020-01-01")]
    result = performance(pos, {"AAPL": 200.0}, USD)
    assert result.total_return_pct == pytest.approx(100.0)
    assert result.annualized_return_pct is not None


def test_performance_negative_return():
    pos = [_pos("AAPL", 10, 200.0, purchased_at="2023-01-01")]
    result = performance(pos, {"AAPL": 100.0}, USD)
    assert result.total_return_pct == pytest.approx(-50.0)


def test_performance_skips_missing_price():
    positions = [
        _pos("AAPL", 10, 100.0, purchased_at="2022-01-01"),
        _pos("GHOST", 10, 100.0, purchased_at="2022-01-01"),
    ]
    result = performance(positions, {"AAPL": 200.0}, USD)
    assert result.total_return_pct == pytest.approx(100.0)


def test_performance_annualized_none_for_short_period():
    # purchased_at is recent — holding period < 0.1 years
    from datetime import date, timedelta
    recent = (date.today() - timedelta(days=5)).isoformat()
    pos = [_pos("AAPL", 10, 100.0, purchased_at=recent)]
    result = performance(pos, {"AAPL": 110.0}, USD)
    assert result.annualized_return_pct is None


def test_performance_multi_currency():
    positions = [
        _pos("ASML", 5, 700.0, currency="EUR", purchased_at="2022-01-01"),
        _pos("AAPL", 10, 150.0, currency="USD", purchased_at="2022-01-01"),
    ]
    prices = {"ASML": 700.0, "AAPL": 150.0}  # no change in local prices
    result = performance(positions, prices, USD_EUR)
    # cost and current are equal → 0% return
    assert result.total_return_pct == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# benchmark_comparison()
# ---------------------------------------------------------------------------

def test_benchmark_comparison_positive_alpha():
    result = benchmark_comparison(18.4, 14.2, "S&P 500")
    assert result.alpha_pct == pytest.approx(4.2)
    assert result.benchmark == "S&P 500"


def test_benchmark_comparison_negative_alpha():
    result = benchmark_comparison(5.0, 12.0, "FTSE 100")
    assert result.alpha_pct == pytest.approx(-7.0)


def test_benchmark_comparison_zero_alpha():
    result = benchmark_comparison(10.0, 10.0, "QQQ")
    assert result.alpha_pct == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# total_value()
# ---------------------------------------------------------------------------

def test_total_value_single_position():
    pos = [_pos("AAPL", 10, 100.0)]
    val = total_value(pos, {"AAPL": 150.0}, USD)
    assert val == pytest.approx(1500.0)


def test_total_value_skips_missing():
    pos = [_pos("AAPL", 10, 100.0), _pos("GHOST", 10, 100.0)]
    val = total_value(pos, {"AAPL": 150.0}, USD)
    assert val == pytest.approx(1500.0)


def test_total_value_multi_currency():
    pos = [
        _pos("ASML", 2, 700.0, currency="EUR"),
        _pos("AAPL", 5, 150.0, currency="USD"),
    ]
    prices = {"ASML": 800.0, "AAPL": 160.0}
    val = total_value(pos, prices, USD_EUR)
    # EUR: 2 * 800 * 1.08 = 1728; USD: 5 * 160 = 800
    assert val == pytest.approx(2528.0)
