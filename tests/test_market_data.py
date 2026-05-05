"""
MarketData tests — yfinance is fully mocked; no real network calls.
"""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.market_data import BENCHMARK_SYMBOLS, MarketData


def _mock_ticker(last_price=None, history_df=None):
    """Build a mock yf.Ticker instance."""
    t = MagicMock()
    fi = MagicMock()
    fi.last_price = last_price
    t.fast_info = fi
    t.history.return_value = history_df if history_df is not None else pd.DataFrame()
    return t


# ---------------------------------------------------------------------------
# get_prices
# ---------------------------------------------------------------------------

def test_get_prices_returns_price_from_fast_info(mocker):
    mock_t = _mock_ticker(last_price=150.0)
    mocker.patch("src.market_data.yf.Ticker", return_value=mock_t)

    md = MarketData()
    prices = md.get_prices(["AAPL"])
    assert prices == {"AAPL": 150.0}


def test_get_prices_falls_back_to_history_when_fast_info_missing(mocker):
    hist = pd.DataFrame({"Close": [148.0]})
    mock_t = _mock_ticker(last_price=None, history_df=hist)
    mocker.patch("src.market_data.yf.Ticker", return_value=mock_t)

    md = MarketData()
    prices = md.get_prices(["AAPL"])
    assert prices == {"AAPL": 148.0}


def test_get_prices_skips_missing_ticker(mocker):
    mock_t = _mock_ticker(last_price=None, history_df=pd.DataFrame())
    mocker.patch("src.market_data.yf.Ticker", return_value=mock_t)

    md = MarketData()
    prices = md.get_prices(["GHOST"])
    assert "GHOST" not in prices


def test_get_prices_skips_on_exception(mocker):
    mocker.patch("src.market_data.yf.Ticker", side_effect=RuntimeError("network down"))

    md = MarketData()
    prices = md.get_prices(["AAPL"])
    assert prices == {}


def test_get_prices_caches_within_request(mocker):
    mock_t = _mock_ticker(last_price=150.0)
    patched = mocker.patch("src.market_data.yf.Ticker", return_value=mock_t)

    md = MarketData()
    md.get_prices(["AAPL"])
    md.get_prices(["AAPL"])  # second call must use cache

    # yf.Ticker should only be called once despite two get_prices calls
    assert patched.call_count == 1


def test_get_prices_multiple_tickers(mocker):
    def make_ticker(symbol):
        prices = {"AAPL": 150.0, "MSFT": 300.0}
        return _mock_ticker(last_price=prices.get(symbol))

    mocker.patch("src.market_data.yf.Ticker", side_effect=make_ticker)

    md = MarketData()
    prices = md.get_prices(["AAPL", "MSFT"])
    assert prices["AAPL"] == 150.0
    assert prices["MSFT"] == 300.0


# ---------------------------------------------------------------------------
# get_fx_rates
# ---------------------------------------------------------------------------

def test_get_fx_rates_base_is_always_1(mocker):
    mocker.patch("src.market_data.yf.Ticker", return_value=_mock_ticker(last_price=1.0))
    md = MarketData()
    rates = md.get_fx_rates(["USD"], base="USD")
    assert rates["USD"] == 1.0


def test_get_fx_rates_returns_eur_rate(mocker):
    mock_t = _mock_ticker(last_price=1.08)
    mocker.patch("src.market_data.yf.Ticker", return_value=mock_t)

    md = MarketData()
    rates = md.get_fx_rates(["EUR"], base="USD")
    assert rates["EUR"] == pytest.approx(1.08)


def test_get_fx_rates_skips_on_exception(mocker):
    mocker.patch("src.market_data.yf.Ticker", side_effect=RuntimeError("no network"))

    md = MarketData()
    rates = md.get_fx_rates(["EUR"], base="USD")
    assert "EUR" not in rates
    assert rates["USD"] == 1.0


def test_get_fx_rates_caches_within_request(mocker):
    patched = mocker.patch(
        "src.market_data.yf.Ticker", return_value=_mock_ticker(last_price=1.08)
    )
    md = MarketData()
    md.get_fx_rates(["EUR"], base="USD")
    md.get_fx_rates(["EUR"], base="USD")
    assert patched.call_count == 1


# ---------------------------------------------------------------------------
# get_benchmark_return
# ---------------------------------------------------------------------------

def test_get_benchmark_return_by_canonical_name(mocker):
    hist = pd.DataFrame({"Close": [100.0, 110.0]})
    mocker.patch("src.market_data.yf.Ticker", return_value=_mock_ticker(history_df=hist))

    md = MarketData()
    ret = md.get_benchmark_return("S&P 500")
    assert ret == pytest.approx(10.0)


def test_get_benchmark_return_maps_name_to_symbol(mocker):
    hist = pd.DataFrame({"Close": [200.0, 220.0]})
    patched = mocker.patch(
        "src.market_data.yf.Ticker", return_value=_mock_ticker(history_df=hist)
    )
    md = MarketData()
    md.get_benchmark_return("S&P 500")
    patched.assert_called_with("^GSPC")


def test_get_benchmark_return_returns_zero_on_error(mocker):
    mocker.patch("src.market_data.yf.Ticker", side_effect=RuntimeError("error"))

    md = MarketData()
    ret = md.get_benchmark_return("S&P 500")
    assert ret == 0.0


def test_get_benchmark_return_caches(mocker):
    hist = pd.DataFrame({"Close": [100.0, 115.0]})
    patched = mocker.patch(
        "src.market_data.yf.Ticker", return_value=_mock_ticker(history_df=hist)
    )
    md = MarketData()
    md.get_benchmark_return("QQQ")
    md.get_benchmark_return("QQQ")
    assert patched.call_count == 1


def test_benchmark_symbols_contains_major_indices():
    assert "S&P 500" in BENCHMARK_SYMBOLS
    assert "FTSE 100" in BENCHMARK_SYMBOLS
    assert "NIKKEI 225" in BENCHMARK_SYMBOLS
    assert "MSCI World" in BENCHMARK_SYMBOLS
