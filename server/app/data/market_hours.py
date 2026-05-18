from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketHours:
    tz: str
    open: time
    close: time


MARKET_HOURS: dict[str, MarketHours] = {
    "US": MarketHours("America/New_York", time(9, 30), time(16, 0)),
    "CN": MarketHours("Asia/Shanghai", time(9, 30), time(15, 0)),
    "HK": MarketHours("Asia/Hong_Kong", time(9, 30), time(16, 0)),
    "JP": MarketHours("Asia/Tokyo", time(9, 0), time(15, 0)),
    "KR": MarketHours("Asia/Seoul", time(9, 0), time(15, 30)),
}


def _config(market: str) -> MarketHours:
    return MARKET_HOURS.get(market.upper(), MARKET_HOURS["US"])


def tz_of(market: str) -> ZoneInfo:
    return ZoneInfo(_config(market).tz)


def open_time_of(market: str) -> time:
    return _config(market).open


def close_time_of(market: str) -> time:
    return _config(market).close


def _as_aware_utc(at: datetime) -> datetime:
    if at.tzinfo is None:
        return at.replace(tzinfo=timezone.utc)
    return at.astimezone(timezone.utc)


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5


def previous_trading_day(market: str, day: date) -> date:
    cur = day - timedelta(days=1)
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur


def ref_trading_day(market: str, at: datetime) -> date:
    cfg = _config(market)
    now_local = _as_aware_utc(at).astimezone(ZoneInfo(cfg.tz))
    today = now_local.date()
    if is_trading_day(today) and now_local.time() >= cfg.open:
        return today
    return previous_trading_day(market, today)


def is_open(market: str, at: datetime) -> bool:
    cfg = _config(market)
    now_local = _as_aware_utc(at).astimezone(ZoneInfo(cfg.tz))
    return (
        is_trading_day(now_local.date())
        and cfg.open <= now_local.time() <= cfg.close
    )


def market_status(market: str, at: datetime) -> str:
    return "open" if is_open(market, at) else "closed"
