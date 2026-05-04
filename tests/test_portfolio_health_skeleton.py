"""
Portfolio Health agent tests.

Uses injected mock market data so no network calls are made.
"""
from typing import Dict, Optional
from unittest.mock import MagicMock

import pytest

from src.agents.portfolio_health import run


# ---------------------------------------------------------------------------
# Shared mock market data factory
# ---------------------------------------------------------------------------

def _mock_md(
    prices: Optional[Dict] = None,
    fx_rates: Optional[Dict] = None,
    benchmark_return: float = 14.0,
) -> MagicMock:
    md = MagicMock()
    md.get_prices.return_value = prices or {}
    md.get_fx_rates.return_value = fx_rates or {"USD": 1.0}
    md.get_benchmark_return.return_value = benchmark_return
    return md


# ---------------------------------------------------------------------------
# Empty portfolio
# ---------------------------------------------------------------------------

def test_portfolio_health_does_not_crash_on_empty_portfolio(load_user, mock_llm):
    """user_004 has no positions. Agent must return a BUILD response without crashing."""
    user = load_user("usr_004")
    # Empty portfolio never needs market data, but inject anyway to be safe
    response = run(user, llm=mock_llm, market_data=_mock_md())

    assert response is not None
    assert "disclaimer" in response
    assert "not investment advice" in response["disclaimer"].lower()


def test_empty_portfolio_observations_are_build_oriented(load_user, mock_llm):
    """Observations for an empty portfolio must guide the user to start building."""
    user = load_user("usr_004")
    response = run(user, llm=mock_llm, market_data=_mock_md())

    obs_texts = " ".join(o["text"].lower() for o in response["observations"])
    assert any(
        word in obs_texts
        for word in ("start", "etf", "diversif", "build", "invest")
    ), f"Expected BUILD-oriented language in observations, got: {obs_texts}"


def test_empty_portfolio_total_value_is_zero(load_user, mock_llm):
    user = load_user("usr_004")
    response = run(user, llm=mock_llm, market_data=_mock_md())
    assert response["total_value"] == 0.0


# ---------------------------------------------------------------------------
# Concentration
# ---------------------------------------------------------------------------

def test_portfolio_health_flags_concentration(load_user, mock_llm):
    """
    usr_003 has NVDA at ~180 shares × $500 = $90k out of ~$99k total → >90% concentration.
    Agent must surface a high/warning flag.
    """
    # usr_003 positions: NVDA, VTI, VXUS, BND, AAPL
    prices = {
        "NVDA": 500.0,
        "VTI": 200.0,
        "VXUS": 55.0,
        "BND": 70.0,
        "AAPL": 170.0,
    }
    user = load_user("usr_003")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices))

    assert response["concentration_risk"]["flag"] == "high"
    assert response["concentration_risk"]["top_position_pct"] > 80.0


def test_concentration_warning_in_observations(load_user, mock_llm):
    """High concentration must produce a warning observation mentioning the top ticker."""
    prices = {
        "NVDA": 500.0,
        "VTI": 200.0,
        "VXUS": 55.0,
        "BND": 70.0,
        "AAPL": 170.0,
    }
    user = load_user("usr_003")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices))

    warnings = [o for o in response["observations"] if o["severity"] == "warning"]
    assert warnings, "Expected at least one warning observation for high concentration"
    assert any("NVDA" in o["text"] for o in warnings)


# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------

def test_portfolio_health_includes_disclaimer(load_user, mock_llm):
    """All responses must carry 'not investment advice' in the disclaimer."""
    prices = {
        "AAPL": 190.0,
        "MSFT": 420.0,
        "NVDA": 870.0,
        "GOOGL": 170.0,
        "META": 490.0,
        "AMZN": 185.0,
        "TSLA": 175.0,
        "AMD": 145.0,
        "QQQ": 480.0,
    }
    user = load_user("usr_001")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices))

    assert response["disclaimer"]
    assert "not investment advice" in response["disclaimer"].lower()


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------

def test_portfolio_health_result_shape(load_user, mock_llm):
    """Response must contain all required top-level keys."""
    prices = {
        "AAPL": 190.0,
        "MSFT": 420.0,
        "NVDA": 870.0,
        "GOOGL": 170.0,
        "META": 490.0,
        "AMZN": 185.0,
        "TSLA": 175.0,
        "AMD": 145.0,
        "QQQ": 480.0,
    }
    user = load_user("usr_001")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices))

    for key in ("concentration_risk", "performance", "benchmark_comparison", "observations", "disclaimer"):
        assert key in response, f"Missing key: {key}"

    cr = response["concentration_risk"]
    assert "top_position_pct" in cr
    assert "top_3_positions_pct" in cr
    assert cr["flag"] in {"low", "moderate", "high"}

    perf = response["performance"]
    assert "total_return_pct" in perf

    bench = response["benchmark_comparison"]
    assert "benchmark" in bench
    assert "alpha_pct" in bench

    assert isinstance(response["observations"], list)


def test_observations_have_severity_and_text(load_user, mock_llm):
    """Every observation must have 'severity' and 'text' fields."""
    prices = {"NVDA": 500.0, "VTI": 200.0, "VXUS": 55.0, "BND": 70.0, "AAPL": 170.0}
    user = load_user("usr_003")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices))

    for obs in response["observations"]:
        assert "severity" in obs
        assert "text" in obs
        assert obs["severity"] in {"info", "warning", "critical"}


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

def test_performance_total_return_present(load_user, mock_llm):
    """total_return_pct must be a float (can be negative)."""
    prices = {"NVDA": 500.0, "VTI": 200.0, "VXUS": 55.0, "BND": 70.0, "AAPL": 170.0}
    user = load_user("usr_003")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices))

    assert isinstance(response["performance"]["total_return_pct"], float)


# ---------------------------------------------------------------------------
# Benchmark comparison
# ---------------------------------------------------------------------------

def test_benchmark_comparison_uses_preferred_benchmark(load_user, mock_llm):
    """Benchmark comparison must reference the user's preferred benchmark."""
    prices = {
        "AAPL": 190.0, "MSFT": 420.0, "NVDA": 870.0, "GOOGL": 170.0,
        "META": 490.0, "AMZN": 185.0, "TSLA": 175.0, "AMD": 145.0, "QQQ": 480.0,
    }
    user = load_user("usr_001")  # prefers QQQ
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices))

    assert response["benchmark_comparison"]["benchmark"] == "QQQ"


def test_alpha_calculation(load_user, mock_llm):
    """alpha_pct must equal portfolio_return_pct - benchmark_return_pct."""
    prices = {"NVDA": 500.0, "VTI": 200.0, "VXUS": 55.0, "BND": 70.0, "AAPL": 170.0}
    user = load_user("usr_003")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices, benchmark_return=14.0))

    bench = response["benchmark_comparison"]
    expected_alpha = round(bench["portfolio_return_pct"] - bench["benchmark_return_pct"], 2)
    assert abs(bench["alpha_pct"] - expected_alpha) < 0.01


# ---------------------------------------------------------------------------
# Missing prices (graceful degradation)
# ---------------------------------------------------------------------------

def test_missing_prices_do_not_crash(load_user, mock_llm):
    """If market data returns no prices, agent must not crash."""
    user = load_user("usr_003")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices={}))

    assert response is not None
    assert "disclaimer" in response


# ---------------------------------------------------------------------------
# Multi-currency (usr_006) — USD/EUR/GBP/JPY positions
# ---------------------------------------------------------------------------

def test_multi_currency_usr006_does_not_crash(load_user, mock_llm):
    """usr_006 has positions in EUR, GBP, JPY; must not crash."""
    # AAPL/VOO in USD, ASML.AS in EUR, HSBA.L in GBP, 7203.T in JPY
    prices = {
        "AAPL": 190.0,
        "VOO": 480.0,
        "ASML.AS": 700.0,
        "HSBA.L": 7.20,
        "7203.T": 2600.0,
    }
    fx_rates = {"USD": 1.0, "EUR": 1.10, "GBP": 1.28, "JPY": 0.0067}
    user = load_user("usr_006")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices, fx_rates=fx_rates))

    assert response is not None
    assert "disclaimer" in response
    assert "not investment advice" in response["disclaimer"].lower()


def test_multi_currency_fx_conversion_applied(load_user, mock_llm):
    """
    FX conversion must produce a total_value > 0 and concentrate risk should
    be computed in base currency (USD), not raw position currency.
    """
    prices = {
        "AAPL": 190.0,
        "VOO": 480.0,
        "ASML.AS": 700.0,
        "HSBA.L": 7.20,
        "7203.T": 2600.0,
    }
    fx_rates = {"USD": 1.0, "EUR": 1.10, "GBP": 1.28, "JPY": 0.0067}
    user = load_user("usr_006")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices, fx_rates=fx_rates))

    # total_value should reflect USD-converted values, not raw numbers
    # AAPL: 45*190=8550, VOO: 18*480=8640, ASML.AS: 8*700*1.10=6160,
    # HSBA.L: 250*7.20*1.28=2304, 7203.T: 200*2600*0.0067=3484 → ~29138 USD
    assert response["total_value"] > 20_000  # clearly not raw-JPY inflated
    assert response["total_value"] < 50_000  # clearly not JPY-confused (~520k JPY raw)


def test_multi_currency_benchmark_is_msci_world(load_user, mock_llm):
    """usr_006 prefers MSCI World benchmark — must be reflected in comparison."""
    prices = {"AAPL": 190.0, "VOO": 480.0, "ASML.AS": 700.0, "HSBA.L": 7.20, "7203.T": 2600.0}
    fx_rates = {"USD": 1.0, "EUR": 1.10, "GBP": 1.28, "JPY": 0.0067}
    user = load_user("usr_006")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices, fx_rates=fx_rates))

    assert response["benchmark_comparison"]["benchmark"] == "MSCI World"


# ---------------------------------------------------------------------------
# Retiree portfolio (usr_008) — conservative, all USD, 7 positions
# ---------------------------------------------------------------------------

def test_retiree_usr008_does_not_crash(load_user, mock_llm):
    """usr_008 is a conservative dividend retiree — must not crash."""
    prices = {
        "JNJ": 155.0, "PG": 160.0, "KO": 65.0,
        "VYM": 120.0, "SCHD": 85.0, "BND": 72.0, "TLT": 95.0,
    }
    user = load_user("usr_008")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices))

    assert response is not None
    assert "disclaimer" in response
    assert "not investment advice" in response["disclaimer"].lower()


def test_retiree_diversified_portfolio_is_low_or_moderate_concentration(load_user, mock_llm):
    """
    usr_008 holds 7 positions with no single dominant holding;
    concentration flag should not be 'high'.
    """
    prices = {
        "JNJ": 155.0, "PG": 160.0, "KO": 65.0,
        "VYM": 120.0, "SCHD": 85.0, "BND": 72.0, "TLT": 95.0,
    }
    user = load_user("usr_008")
    response = run(user, llm=mock_llm, market_data=_mock_md(prices=prices))

    assert response["concentration_risk"]["flag"] in {"low", "moderate"}
