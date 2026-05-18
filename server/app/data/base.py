from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class DataSourceError(Exception):
    """Raised when a data source cannot fulfil a request."""


class DataSource(ABC):
    """Abstract market data provider.

    Implementations must return tz-naive pandas Series so downstream
    metrics/caching code does not need to handle timezone arithmetic.
    """

    name: str

    @abstractmethod
    def get_prices(self, symbol: str, start: date, end: date) -> pd.Series:
        """Adjusted close price series indexed by trading day."""

    @abstractmethod
    def get_dividends(
        self, symbol: str, start: date, end: date
    ) -> pd.Series | None:
        """Cash dividend amounts indexed by ex-dividend date.

        Return None when the source does not provide dividends or the symbol
        has none in the window. Callers must treat None as "indicator not
        available" rather than zero.
        """

    def get_ohlc(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Adjusted OHLC dataframe with columns Open/High/Low/Close/Volume.

        Default implementation derives a synthetic frame from get_prices so
        sources without true OHLC still return something candlestick-shaped
        (open == close == high == low). Override for real OHLC.
        """
        prices = self.get_prices(symbol, start, end)
        return pd.DataFrame({
            "Open": prices, "High": prices, "Low": prices, "Close": prices,
            "Volume": 0,
        })

    def get_fresh_ohlc(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Adjusted OHLC that should not use long-lived daily caches.

        This is intended for same-session display reconciliation, where a daily
        cache populated before the official close can otherwise make an index
        card keep showing a stale intraday value after the market has closed.
        """
        return self.get_ohlc(symbol, start, end)

    def get_raw_ohlc(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Execution OHLC in the closest available real-trading price basis.

        Implementations that can distinguish adjusted vs. raw prices should
        override this. The default preserves backwards compatibility for test
        and fallback data sources.
        """
        return self.get_ohlc(symbol, start, end)

    def get_splits(self, symbol: str, start: date, end: date) -> pd.Series | None:
        """Stock split ratios indexed by effective date.

        A 2-for-1 split should be represented as 2.0. Return None when the
        source has no split data for the requested window.
        """
        return None

    def get_cash_dividends(
        self, symbol: str, start: date, end: date
    ) -> pd.Series | None:
        """Cash dividends per share in execution price basis."""
        return self.get_dividends(symbol, start, end)

    def get_info(self, symbol: str) -> dict | None:
        """Snapshot fundamentals: pe_ratio, market_cap, week52_high/low,
        dividend_yield, volume, name. Return None when unavailable."""
        return None

    def get_quote(self, symbol: str) -> dict | None:
        """Latest quote snapshot for display-only price and change fields."""
        return None

    def get_exchange(self, symbol: str) -> str | None:
        """Best-effort exchange code/name for benchmark selection."""
        info = self.get_info(symbol)
        if not info:
            return None
        for key in ("exchange", "full_exchange_name", "exchange_name"):
            value = info.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def get_intraday_prices(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.Series:
        """Intraday close price series indexed by timestamp."""
        raise DataSourceError("intraday prices are not supported by this data source")

    def get_intraday_prices_tz(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.Series:
        """Intraday close price series preserving source timezone when available."""
        return self.get_intraday_prices(symbol, period=period, interval=interval)

    def get_intraday_ohlc(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.DataFrame:
        """Intraday OHLC dataframe indexed by timestamp."""
        prices = self.get_intraday_prices(symbol, period=period, interval=interval)
        return pd.DataFrame({
            "Open": prices, "High": prices, "Low": prices, "Close": prices,
            "Volume": 0,
        })

    def get_intraday_ohlc_tz(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.DataFrame:
        """Intraday OHLC preserving source timezone when available."""
        prices = self.get_intraday_prices_tz(symbol, period=period, interval=interval)
        return pd.DataFrame({
            "Open": prices, "High": prices, "Low": prices, "Close": prices,
            "Volume": 0,
        })
