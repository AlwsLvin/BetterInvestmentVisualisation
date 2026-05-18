from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import isfinite
from numbers import Real

import pandas as pd

from app.data.base import DataSource, DataSourceError
from app.data.market_hours import close_time_of, market_status, ref_trading_day, tz_of
from app.data.symbols import market_of


def _finite_positive(value) -> float | None:
    if isinstance(value, Real) and isfinite(float(value)) and float(value) > 0:
        return float(value)
    return None


def _finite_number(value) -> float | None:
    if isinstance(value, Real) and isfinite(float(value)):
        return float(value)
    return None


def _display_time(value, display_tz) -> pd.Timestamp | None:
    if not isinstance(value, datetime):
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    return ts.tz_convert(display_tz).tz_localize(None)


def _daily_close_on(
    src: DataSource,
    symbol: str,
    ref_day: date,
    fresh: bool = False,
) -> float | None:
    try:
        df = (
            src.get_fresh_ohlc(symbol, ref_day, ref_day)
            if fresh else src.get_ohlc(symbol, ref_day, ref_day)
        )
    except DataSourceError:
        return None
    if df.empty or "Close" not in df.columns:
        return None
    frame = df.sort_index()
    if isinstance(frame.index, pd.DatetimeIndex):
        frame = frame[frame.index.normalize() == pd.Timestamp(ref_day)]
    close = frame["Close"].dropna()
    if close.empty:
        return None
    return _finite_positive(close.iloc[-1])


def _previous_close_before(
    src: DataSource,
    symbol: str,
    ref_day: date,
) -> float | None:
    try:
        df = src.get_ohlc(symbol, ref_day - timedelta(days=14), ref_day - timedelta(days=1))
    except DataSourceError:
        return None
    if df.empty or "Close" not in df.columns:
        return None
    frame = df.sort_index()
    if isinstance(frame.index, pd.DatetimeIndex):
        frame = frame[frame.index.normalize() < pd.Timestamp(ref_day)]
    close = frame["Close"].dropna()
    if close.empty:
        return None
    return _finite_positive(close.iloc[-1])


def _recent_raw_close_pair(
    src: DataSource,
    symbol: str,
    ref_day: date,
) -> tuple[float | None, float | None, datetime | None]:
    try:
        df = src.get_raw_ohlc(symbol, ref_day - timedelta(days=14), ref_day)
    except DataSourceError:
        return None, None, None
    if df.empty or "Close" not in df.columns:
        return None, None, None
    close = df.sort_index()["Close"].dropna()
    if len(close) < 2:
        return None, None, None
    latest = _finite_positive(close.iloc[-1])
    previous = _finite_positive(close.iloc[-2])
    if latest is None or previous is None:
        return None, None, None
    latest_idx = pd.Timestamp(close.index[-1])
    if latest_idx.time() == time(0, 0):
        as_of = datetime.combine(latest_idx.date(), time(0, 0), tzinfo=timezone.utc)
    else:
        if latest_idx.tzinfo is None:
            latest_idx = latest_idx.tz_localize(timezone.utc)
        as_of = latest_idx.to_pydatetime()
    return latest, previous, as_of


def _market_close_as_of(market: str, ref_day: date) -> datetime:
    return datetime.combine(ref_day, close_time_of(market), tzinfo=tz_of(market))


def display_quote(
    src: DataSource,
    symbol: str,
    now: datetime | None = None,
) -> dict | None:
    """Build the display-only quote used for latest price and daily change.

    Non-intraday views still need a true daily-change snapshot. A historical
    range's last two points are not necessarily "today", so this helper keeps
    that display field tied to quote/fresh daily close data instead.
    """
    market = market_of(symbol)
    at = now or datetime.now(timezone.utc)
    ref_day = ref_trading_day(market, at)
    status = market_status(market, at)
    market_tz = tz_of(market)

    try:
        raw = src.get_quote(symbol) or {}
    except Exception:
        raw = {}
    quote_last = _finite_positive(raw.get("last_price"))
    quote_previous = _finite_positive(raw.get("previous_close"))
    quote_change = _finite_number(raw.get("change_pct"))
    as_of = raw.get("as_of")

    quote_target = _display_time(as_of, market_tz)
    quote_stale = quote_target is not None and (
        quote_target.date() < ref_day
        or (status == "closed" and quote_target.date() > ref_day)
    )
    if quote_stale:
        quote_last = None
        quote_previous = None
        quote_change = None

    daily_close = _daily_close_on(src, symbol, ref_day, fresh=True) if status == "closed" else None

    if daily_close is not None:
        previous = _previous_close_before(src, symbol, ref_day) or quote_previous
        change = daily_close / previous - 1.0 if previous is not None else None
        return {
            "last_price": daily_close,
            "previous_close": previous,
            "change_pct": change,
            "as_of": _market_close_as_of(market, ref_day),
            "source": "daily_close",
        }

    if quote_last is not None or quote_previous is not None:
        change = quote_change
        if change is None and quote_last is not None and quote_previous is not None:
            change = quote_last / quote_previous - 1.0
        return {
            "last_price": quote_last,
            "previous_close": quote_previous,
            "change_pct": change,
            "as_of": as_of,
            "source": "quote_snapshot",
        }

    latest, previous, raw_as_of = _recent_raw_close_pair(src, symbol, ref_day)
    if latest is None and previous is None:
        return None
    change = latest / previous - 1.0 if latest is not None and previous is not None else None
    return {
        "last_price": latest,
        "previous_close": previous,
        "change_pct": change,
        "as_of": raw_as_of,
        "source": "raw_daily_fallback",
    }
