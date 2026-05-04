"""
Market data wrapper around yfinance.

Per-instance cache means repeated lookups within one request never
hit the network twice. All methods swallow exceptions and return
safe defaults so the pipeline never crashes on a bad ticker.
"""
import logging
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Benchmark name → yfinance symbol
# ---------------------------------------------------------------------------

BENCHMARK_SYMBOLS: Dict[str, str] = {
    "S&P 500": "^GSPC",
    "FTSE 100": "^FTSE",
    "NIKKEI 225": "^N225",
    "MSCI World": "URTH",
    "QQQ": "QQQ",
    "NASDAQ": "^IXIC",
    "ASX 200": "^AXJO",
    "STI": "^STI",
}


class MarketData:
    """
    Lightweight yfinance façade with per-request caching.

    Instantiate once per agent call; do not share across requests.
    """

    def __init__(self) -> None:
        self._price_cache: Dict[str, float] = {}
        self._fx_cache: Dict[str, float] = {}
        self._benchmark_cache: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Return {ticker: current_price_in_ticker_currency}.

        Missing or errored tickers are silently omitted — callers must
        handle the case where a ticker is not in the result.
        """
        result: Dict[str, float] = {}
        for ticker in tickers:
            price = self._price_cache.get(ticker)
            if price is None:
                price = self._fetch_price(ticker)
                if price is not None:
                    self._price_cache[ticker] = price
            if price is not None:
                result[ticker] = price
        return result

    def get_fx_rates(
        self, currencies: List[str], base: str = "USD"
    ) -> Dict[str, float]:
        """
        Return {currency: rate_to_base}.

        The base currency always maps to 1.0.
        Unknown or failed currencies are omitted.
        """
        result: Dict[str, float] = {base: 1.0}
        for currency in currencies:
            if currency == base:
                continue
            cache_key = f"{currency}{base}"
            rate = self._fx_cache.get(cache_key)
            if rate is None:
                rate = self._fetch_fx_rate(currency, base)
                if rate is not None:
                    self._fx_cache[cache_key] = rate
            if rate is not None:
                result[currency] = rate
        return result

    def get_benchmark_return(self, benchmark_name: str, period: str = "1y") -> float:
        """
        Return the percentage return of a benchmark over `period`.

        `benchmark_name` can be a canonical name ("S&P 500") or a
        yfinance ticker ("^GSPC", "QQQ"). Returns 0.0 on failure.
        """
        symbol = BENCHMARK_SYMBOLS.get(benchmark_name, benchmark_name)
        cache_key = f"{symbol}_{period}"
        cached = self._benchmark_cache.get(cache_key)
        if cached is not None:
            return cached
        ret = self._fetch_benchmark_return(symbol, period)
        self._benchmark_cache[cache_key] = ret
        return ret

    # ------------------------------------------------------------------
    # Private fetch helpers — each wrapped in try/except
    # ------------------------------------------------------------------

    def _fetch_price(self, ticker: str) -> Optional[float]:
        try:
            info = yf.Ticker(ticker).fast_info
            price = getattr(info, "last_price", None)
            if price is not None:
                return float(price)
            # fallback: last close from 1-day history
            hist = yf.Ticker(ticker).history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as exc:
            logger.warning("Could not fetch price for %s: %s", ticker, exc)
        return None

    def _fetch_fx_rate(self, currency: str, base: str) -> Optional[float]:
        try:
            symbol = f"{currency}{base}=X"
            info = yf.Ticker(symbol).fast_info
            rate = getattr(info, "last_price", None)
            if rate is not None:
                return float(rate)
            hist = yf.Ticker(symbol).history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as exc:
            logger.warning("Could not fetch FX rate %s/%s: %s", currency, base, exc)
        return None

    def _fetch_benchmark_return(self, symbol: str, period: str) -> float:
        try:
            hist = yf.Ticker(symbol).history(period=period)
            if len(hist) >= 2:
                start = float(hist["Close"].iloc[0])
                end = float(hist["Close"].iloc[-1])
                if start > 0:
                    return round(((end - start) / start) * 100, 2)
        except Exception as exc:
            logger.warning("Could not fetch benchmark return for %s: %s", symbol, exc)
        return 0.0
