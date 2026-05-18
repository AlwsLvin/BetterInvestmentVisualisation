from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import isfinite
from numbers import Real
from pathlib import Path
from threading import Lock

import pandas as pd

from app.data.base import DataSource, DataSourceError
from app.data.cache import FileCache
from app.data.symbols import to_yfinance

_MISSING_DIVIDEND_SENTINEL = "__BV_NO_DIVIDEND__"
_YFINANCE_DOWNLOAD_LOCK = Lock()
_YFINANCE_CACHE_CONFIGURED_FOR: Path | None = None


def _configure_yfinance_cache(cache_dir: Path | str | None) -> None:
    global _YFINANCE_CACHE_CONFIGURED_FOR
    if cache_dir is None:
        return
    target = Path(cache_dir)
    if _YFINANCE_CACHE_CONFIGURED_FOR == target:
        return
    try:
        target.mkdir(parents=True, exist_ok=True)
        import yfinance as yf

        setter = getattr(yf, "set_tz_cache_location", None)
        if callable(setter):
            setter(str(target))
            _YFINANCE_CACHE_CONFIGURED_FOR = target
    except Exception:
        pass


def _strip_tz(s: pd.Series) -> pd.Series:
    if s.empty:
        return s
    if isinstance(s.index, pd.DatetimeIndex) and s.index.tz is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)
    s.index = s.index.normalize()
    return s.sort_index()


def _strip_intraday_tz(s: pd.Series) -> pd.Series:
    if s.empty:
        return s
    if isinstance(s.index, pd.DatetimeIndex) and s.index.tz is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)
    return s.sort_index()


def _sort_intraday_keep_tz(s: pd.Series) -> pd.Series:
    if s.empty:
        return s
    return s.sort_index()


def _strip_intraday_ohlc_tz(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    return out.sort_index()


def _sort_intraday_ohlc_keep_tz(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_index()


def _normalize_ohlc(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    out = df[cols].dropna(subset=[c for c in cols if c != "Volume"])
    if isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out.index = out.index.normalize()
    out = out.sort_index()
    out.attrs["symbol"] = symbol
    return out


def _normalize_intraday_ohlc(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    required = [c for c in ("Open", "High", "Low", "Close") if c in cols]
    out = df[cols].dropna(subset=required)
    if out.empty or "Close" not in out.columns:
        raise DataSourceError(f"No intraday OHLC data for {symbol}")
    out = out.sort_index()
    out.attrs["symbol"] = symbol
    return out


def _undo_split_adjustment(frame: pd.DataFrame, splits: pd.Series | None) -> pd.DataFrame:
    """Reconstruct pre-split trading prices from Yahoo's split-adjusted OHLC."""
    if frame.empty or splits is None or splits.empty:
        return frame
    out = frame.copy()
    clean = splits.dropna().sort_index()
    if isinstance(clean.index, pd.DatetimeIndex):
        clean.index = clean.index.tz_localize(None) if clean.index.tz is not None else clean.index
        clean.index = clean.index.normalize()
    price_cols = [c for c in ("Open", "High", "Low", "Close") if c in out.columns]
    for split_day, ratio_value in clean.items():
        ratio = _finite_float(ratio_value)
        if ratio is None or ratio <= 0 or ratio == 1:
            continue
        mask = out.index < pd.Timestamp(split_day)
        if not mask.any():
            continue
        out.loc[mask, price_cols] = out.loc[mask, price_cols] * ratio
        if "Volume" in out.columns:
            out.loc[mask, "Volume"] = out.loc[mask, "Volume"] / ratio
    return out


def _undo_split_adjusted_dividends(dividends: pd.Series, splits: pd.Series | None) -> pd.Series:
    if dividends.empty or splits is None or splits.empty:
        return dividends
    out = dividends.copy()
    clean = splits.dropna().sort_index()
    if isinstance(clean.index, pd.DatetimeIndex):
        clean.index = clean.index.tz_localize(None) if clean.index.tz is not None else clean.index
        clean.index = clean.index.normalize()
    for split_day, ratio_value in clean.items():
        ratio = _finite_float(ratio_value)
        if ratio is None or ratio <= 0 or ratio == 1:
            continue
        mask = out.index < pd.Timestamp(split_day)
        if mask.any():
            out.loc[mask] = out.loc[mask] * ratio
    return out.sort_index()


def _finite_float(value) -> float | None:
    if isinstance(value, Real) and isfinite(float(value)):
        return float(value)
    return None


def _quote_time(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, Real) and isfinite(float(value)) and value > 0:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    return None


class YFinanceSource(DataSource):
    name = "yfinance"

    def __init__(
        self,
        cache: FileCache | None = None,
        intraday_cache: FileCache | None = None,
    ):
        self.cache = cache
        self.intraday_cache = intraday_cache if intraday_cache is not None else cache
        base_cache_dir = (
            self.cache.cache_dir
            if self.cache is not None
            else Path(__file__).resolve().parents[2] / ".cache"
        )
        _configure_yfinance_cache(base_cache_dir / "yfinance")

    def _cache_key(self, kind: str, symbol: str, start: date, end: date) -> str:
        return f"yf:{kind}:{symbol}:{start.isoformat()}:{end.isoformat()}"

    def get_prices(self, symbol: str, start: date, end: date) -> pd.Series:
        key = self._cache_key("px:v2", symbol, start, end)
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return _strip_tz(cached)

        import yfinance as yf

        yf_symbol = to_yfinance(symbol)
        with _YFINANCE_DOWNLOAD_LOCK:
            df = yf.download(
                yf_symbol,
                start=start,
                end=end + timedelta(days=1),
                progress=False,
                auto_adjust=True,
                actions=False,
                threads=False,
            )
        if df is None or df.empty:
            raise DataSourceError(f"No price data for {symbol} ({yf_symbol})")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if "Close" not in df.columns:
            raise DataSourceError(f"yfinance returned no Close column for {symbol}")

        prices = df["Close"].dropna()
        prices.name = symbol
        prices = _strip_tz(prices)

        if self.cache is not None:
            self.cache.set(key, prices)
        return prices

    def get_ohlc(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        key = self._cache_key("ohlc:v2", symbol, start, end)
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return cached.sort_index()

        import yfinance as yf

        yf_symbol = to_yfinance(symbol)
        with _YFINANCE_DOWNLOAD_LOCK:
            df = yf.download(
                yf_symbol, start=start, end=end + timedelta(days=1),
                progress=False, auto_adjust=True, actions=False,
                threads=False,
            )
        if df is None or df.empty:
            raise DataSourceError(f"No OHLC data for {symbol} ({yf_symbol})")
        df = _normalize_ohlc(df, symbol)

        if self.cache is not None:
            self.cache.set(key, df)
        return df

    def get_fresh_ohlc(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        key = self._cache_key("ohlc_fresh:v1", symbol, start, end)
        cache = self.intraday_cache if self.intraday_cache is not None else None
        if cache is not None:
            cached = cache.get(key)
            if cached is not None:
                return cached.sort_index()

        import yfinance as yf

        yf_symbol = to_yfinance(symbol)
        with _YFINANCE_DOWNLOAD_LOCK:
            df = yf.download(
                yf_symbol, start=start, end=end + timedelta(days=1),
                progress=False, auto_adjust=True, actions=False,
                threads=False,
            )
        if df is None or df.empty:
            raise DataSourceError(f"No fresh OHLC data for {symbol} ({yf_symbol})")
        df = _normalize_ohlc(df, symbol)

        if cache is not None:
            cache.set(key, df)
        return df

    def get_raw_ohlc(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        key = self._cache_key("ohlc_raw:v1", symbol, start, end)
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return cached.sort_index()

        import yfinance as yf

        yf_symbol = to_yfinance(symbol)
        with _YFINANCE_DOWNLOAD_LOCK:
            df = yf.download(
                yf_symbol, start=start, end=end + timedelta(days=1),
                progress=False, auto_adjust=False, actions=False,
                threads=False,
            )
        if df is None or df.empty:
            raise DataSourceError(f"No raw OHLC data for {symbol} ({yf_symbol})")
        out = _normalize_ohlc(df, symbol)
        out = _undo_split_adjustment(out, self.get_splits(symbol, start, end))

        if self.cache is not None:
            self.cache.set(key, out)
        return out

    def _download_intraday_prices(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.Series:
        frame = self._download_intraday_ohlc(symbol, period=period, interval=interval)
        prices = frame["Close"].dropna()
        if prices.empty:
            yf_symbol = to_yfinance(symbol)
            raise DataSourceError(f"No intraday close data for {symbol} ({yf_symbol})")
        prices.name = symbol
        return prices

    def _download_intraday_ohlc(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.DataFrame:
        import yfinance as yf

        yf_symbol = to_yfinance(symbol)
        with _YFINANCE_DOWNLOAD_LOCK:
            df = yf.download(
                yf_symbol,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
                actions=False,
                threads=False,
            )
        if df is None or df.empty:
            raise DataSourceError(f"No intraday data for {symbol} ({yf_symbol})")

        return _normalize_intraday_ohlc(df, symbol)

    def get_intraday_prices(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.Series:
        key = f"yf:intraday:v2:{symbol}:{period}:{interval}"
        if self.intraday_cache is not None:
            cached = self.intraday_cache.get(key)
            if cached is not None:
                return _strip_intraday_tz(cached)

        prices = _strip_intraday_tz(
            self._download_intraday_prices(symbol, period=period, interval=interval)
        )

        if self.intraday_cache is not None:
            self.intraday_cache.set(key, prices)
        return prices

    def get_intraday_prices_tz(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.Series:
        key = f"yf:intraday_tz:v3:{symbol}:{period}:{interval}"
        if self.intraday_cache is not None:
            cached = self.intraday_cache.get(key)
            if cached is not None:
                return _sort_intraday_keep_tz(cached)

        prices = _sort_intraday_keep_tz(
            self._download_intraday_prices(symbol, period=period, interval=interval)
        )

        if self.intraday_cache is not None:
            self.intraday_cache.set(key, prices)
        return prices

    def get_intraday_ohlc(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.DataFrame:
        key = f"yf:intraday_ohlc:v1:{symbol}:{period}:{interval}"
        if self.intraday_cache is not None:
            cached = self.intraday_cache.get(key)
            if cached is not None:
                return _strip_intraday_ohlc_tz(cached)

        frame = _strip_intraday_ohlc_tz(
            self._download_intraday_ohlc(symbol, period=period, interval=interval)
        )

        if self.intraday_cache is not None:
            self.intraday_cache.set(key, frame)
        return frame

    def get_intraday_ohlc_tz(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.DataFrame:
        key = f"yf:intraday_ohlc_tz:v1:{symbol}:{period}:{interval}"
        if self.intraday_cache is not None:
            cached = self.intraday_cache.get(key)
            if cached is not None:
                return _sort_intraday_ohlc_keep_tz(cached)

        frame = _sort_intraday_ohlc_keep_tz(
            self._download_intraday_ohlc(symbol, period=period, interval=interval)
        )

        if self.intraday_cache is not None:
            self.intraday_cache.set(key, frame)
        return frame

    def get_quote(self, symbol: str) -> dict | None:
        key = f"yf:quote:v1:{symbol}"
        cache = self.intraday_cache if self.intraday_cache is not None else self.cache
        if cache is not None:
            cached = cache.get(key)
            if cached is not None:
                return cached  # type: ignore[return-value]

        import yfinance as yf

        yf_symbol = to_yfinance(symbol)
        with _YFINANCE_DOWNLOAD_LOCK:
            ticker = yf.Ticker(yf_symbol)

            fast = {}
            try:
                fast = ticker.fast_info or {}
            except Exception:
                fast = {}
            try:
                raw = ticker.info or {}
            except Exception:
                raw = {}

        def pick(*keys: str):
            for source in (fast, raw):
                for k in keys:
                    try:
                        if isinstance(source, dict):
                            value = source.get(k)
                        else:
                            value = getattr(source, k, None)
                    except Exception:
                        value = None
                    if value is not None:
                        return value
            return None

        last = _finite_float(pick("last_price", "regular_market_price", "regularMarketPrice", "currentPrice"))
        previous = _finite_float(pick(
            "previous_close",
            "regular_market_previous_close",
            "regularMarketPreviousClose",
            "previousClose",
        ))
        as_of = _quote_time(pick("last_time", "regularMarketTime"))
        change_pct = (
            last / previous - 1.0
            if last is not None and previous is not None and previous > 0
            else None
        )
        out = {
            "last_price": last,
            "previous_close": previous,
            "change_pct": change_pct,
            "as_of": as_of,
            "source": "yfinance_quote",
        }
        if last is None and previous is None:
            return None
        if cache is not None:
            cache.set(key, out)
        return out

    def get_info(self, symbol: str) -> dict | None:
        key = f"yf:info:{symbol}"
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                if cached == _MISSING_DIVIDEND_SENTINEL:
                    return None
                return cached  # type: ignore[return-value]

        import yfinance as yf

        yf_symbol = to_yfinance(symbol)
        with _YFINANCE_DOWNLOAD_LOCK:
            try:
                raw = yf.Ticker(yf_symbol).info or {}
            except Exception:
                raw = {}
        if not raw:
            if self.cache is not None:
                self.cache.set(key, _MISSING_DIVIDEND_SENTINEL)
            return None

        # yfinance's dividendYield post-0.2.40 is a percent value (e.g. 0.37
        # for a 0.37% yield), not a decimal fraction. Normalise to fraction
        # so callers can format with their usual percent helper.
        raw_div = raw.get("dividendYield")
        div_frac = (raw_div / 100.0) if isinstance(raw_div, (int, float)) else None

        out = {
            "pe_ratio":       raw.get("trailingPE"),
            "market_cap":     raw.get("marketCap"),
            "week52_high":    raw.get("fiftyTwoWeekHigh"),
            "week52_low":     raw.get("fiftyTwoWeekLow"),
            "dividend_yield": div_frac,
            "volume":         raw.get("regularMarketVolume"),
            "name":           raw.get("shortName") or raw.get("longName"),
            "open":           raw.get("regularMarketOpen") or raw.get("open"),
            "day_high":       raw.get("regularMarketDayHigh") or raw.get("dayHigh"),
            "day_low":        raw.get("regularMarketDayLow") or raw.get("dayLow"),
            "previous_close": raw.get("regularMarketPreviousClose") or raw.get("previousClose"),
            "exchange":       raw.get("exchange"),
            "full_exchange_name": raw.get("fullExchangeName"),
        }
        if self.cache is not None:
            self.cache.set(key, out)
        return out

    def get_dividends(
        self, symbol: str, start: date, end: date
    ) -> pd.Series | None:
        key = self._cache_key("div", symbol, start, end)
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                if isinstance(cached, str) and cached == _MISSING_DIVIDEND_SENTINEL:
                    return None
                return _strip_tz(cached)

        import yfinance as yf

        yf_symbol = to_yfinance(symbol)
        with _YFINANCE_DOWNLOAD_LOCK:
            try:
                divs = yf.Ticker(yf_symbol).dividends
            except Exception:
                divs = None

        if divs is None or len(divs) == 0:
            if self.cache is not None:
                self.cache.set(key, _MISSING_DIVIDEND_SENTINEL)
            return None

        divs = _strip_tz(divs)
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        divs = divs[(divs.index >= start_ts) & (divs.index <= end_ts)]
        if divs.empty:
            if self.cache is not None:
                self.cache.set(key, _MISSING_DIVIDEND_SENTINEL)
            return None

        divs.name = symbol
        if self.cache is not None:
            self.cache.set(key, divs)
        return divs

    def get_cash_dividends(
        self, symbol: str, start: date, end: date
    ) -> pd.Series | None:
        divs = self.get_dividends(symbol, start, end)
        if divs is None:
            return None
        return _undo_split_adjusted_dividends(divs, self.get_splits(symbol, start, end))

    def get_splits(self, symbol: str, start: date, end: date) -> pd.Series | None:
        key = self._cache_key("split:v1", symbol, start, end)
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                if isinstance(cached, str) and cached == _MISSING_DIVIDEND_SENTINEL:
                    return None
                return _strip_tz(cached)

        import yfinance as yf

        yf_symbol = to_yfinance(symbol)
        with _YFINANCE_DOWNLOAD_LOCK:
            try:
                splits = yf.Ticker(yf_symbol).splits
            except Exception:
                splits = None

        if splits is None or len(splits) == 0:
            if self.cache is not None:
                self.cache.set(key, _MISSING_DIVIDEND_SENTINEL)
            return None

        splits = _strip_tz(splits)
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        splits = splits[(splits.index >= start_ts) & (splits.index <= end_ts)]
        splits = splits.dropna()
        splits = splits[splits > 0]
        if splits.empty:
            if self.cache is not None:
                self.cache.set(key, _MISSING_DIVIDEND_SENTINEL)
            return None

        splits.name = symbol
        if self.cache is not None:
            self.cache.set(key, splits)
        return splits
