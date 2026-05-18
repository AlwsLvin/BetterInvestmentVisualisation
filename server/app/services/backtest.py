from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import floor
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.data.lot_size import lot_size
from app.data.market_hours import open_time_of, tz_of
from app.data.symbols import currency_of, market_of


@dataclass(frozen=True)
class Plan:
    """Dollar-cost-averaging schedule.

    frequency:
        "daily"          - every trading day
        "weekly:MON"     - every week (MON/TUE/WED/THU/FRI), snapped forward
                           to the next trading day if it falls on a holiday
        "monthly:15"     - every month on day-of-month 15, snapped forward
        "every:30d"      - every 30 calendar days from start_date

    The first trading day in [start, end] is always seeded as a "head"
    buy regardless of frequency, so a 1y backtest starting 2025-05-09
    invests on 2025-05-09 itself (not waiting for the next month-1).

    amount: cash injected per investment date (>0)
    """

    amount: float
    frequency: str = "monthly:1"


@dataclass
class PurchaseEvent:
    ticker: str
    market: str
    timezone: str
    purchased_at_timezone: str
    purchased_at: date | datetime
    currency: str
    price: float
    fx_rate: float
    fx_source: str
    fx_as_of: date | datetime | None
    fx_alignment_note: str | None
    price_usd: float
    shares: float
    total_shares: float


@dataclass(frozen=True)
class FxRateObservation:
    rate: float
    source: str
    as_of: date | datetime | None
    note: str | None = None


@dataclass
class BacktestResult:
    dates: list[pd.Timestamp]
    nav: list[float]
    cash_invested: list[float]
    return_pct: list[float]
    invest_dates: list[pd.Timestamp]
    final_nav: float
    total_invested: float
    cumulative_return: float
    annualized_return: float | None
    max_drawdown: float
    per_asset_final_value: dict[str, float]
    cash_left: dict[str, float]
    purchase_events: list[PurchaseEvent]


def _frequency_to_invest_dates(
    start: date,
    end: date,
    frequency: str,
    trading_days: pd.DatetimeIndex,
) -> list[pd.Timestamp]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    if frequency == "daily":
        candidates = pd.bdate_range(start_ts, end_ts)
    elif frequency.startswith("weekly:"):
        day = frequency.split(":", 1)[1].upper()
        if day not in {"MON", "TUE", "WED", "THU", "FRI"}:
            raise ValueError(f"weekly day must be MON-FRI, got {day}")
        candidates = pd.date_range(start_ts, end_ts, freq=f"W-{day}")
    elif frequency.startswith("monthly:"):
        target_day = int(frequency.split(":", 1)[1])
        if not 1 <= target_day <= 31:
            raise ValueError(f"monthly day must be 1-31, got {target_day}")
        cur = start_ts.normalize().replace(day=1)
        cands = []
        while cur <= end_ts:
            try:
                t = cur.replace(day=target_day)
            except ValueError:
                t = cur + pd.offsets.MonthEnd(0)
            if start_ts <= t <= end_ts:
                cands.append(t)
            cur = cur + pd.DateOffset(months=1)
        candidates = pd.DatetimeIndex(cands)
    elif frequency.startswith("every:"):
        n = int(frequency.split(":", 1)[1].rstrip("d"))
        if n <= 0:
            raise ValueError(f"every:Nd N must be > 0, got {n}")
        cands = []
        cur = start_ts
        while cur <= end_ts:
            cands.append(cur)
            cur += pd.Timedelta(days=n)
        candidates = pd.DatetimeIndex(cands)
    else:
        raise ValueError(f"Unknown frequency: {frequency}")

    snapped: list[pd.Timestamp] = []
    seen: set[pd.Timestamp] = set()

    if len(trading_days) > 0:
        head = trading_days[0]
        snapped.append(head)
        seen.add(head)

    for c in candidates:
        future = trading_days[trading_days >= c]
        if len(future) == 0:
            continue
        td = future[0]
        if td in seen:
            continue
        seen.add(td)
        snapped.append(td)
    return sorted(snapped)


def _irr(cash_flows: list[float], days_offsets: list[int],
         guess: float = 0.1, max_iter: int = 200, tol: float = 1e-9) -> float | None:
    """Newton-Raphson IRR for irregular daily cash flows.

    Returns None if iteration fails to converge (signs make IRR undefined).
    """
    if not cash_flows or all(cf <= 0 for cf in cash_flows) or all(cf >= 0 for cf in cash_flows):
        return None

    r = guess
    for _ in range(max_iter):
        npv = 0.0
        d_npv = 0.0
        for cf, d in zip(cash_flows, days_offsets):
            t = d / 365.25
            base = 1 + r
            if base <= 0:
                return None
            npv += cf * base ** (-t)
            d_npv += -t * cf * base ** (-t - 1)
        if abs(d_npv) < 1e-15:
            return None
        r_new = r - npv / d_npv
        if r_new <= -1:
            r_new = (r - 1) / 2
        if abs(r_new - r) < tol:
            return r_new
        r = r_new
    return None


def _max_drawdown(curve: np.ndarray) -> float:
    if len(curve) < 2:
        return 0.0
    running_peak = -np.inf
    max_dd = 0.0
    for v in curve:
        if v > running_peak:
            running_peak = v
        if running_peak > 0:
            dd = (running_peak - v) / running_peak
        else:
            dd = running_peak - v
        if dd > max_dd:
            max_dd = dd
    return float(max_dd)


def _slice_indexed_frame(
    df: pd.DataFrame,
    start: date,
    end: date,
) -> pd.DataFrame:
    if _has_intraday_index(df.index):
        return df
    start_ts = pd.Timestamp(start)
    end_exclusive = pd.Timestamp(end) + pd.Timedelta(days=1)
    return df.loc[(df.index >= start_ts) & (df.index < end_exclusive)]


def _has_intraday_index(index: pd.Index) -> bool:
    if not isinstance(index, pd.DatetimeIndex) or len(index) == 0:
        return False
    return any(ts.time() != pd.Timestamp(ts.date()).time() for ts in index)


def _as_ohlc_frame(data: pd.Series | pd.DataFrame) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        df = data.copy().sort_index()
        close = df["Close"] if "Close" in df.columns else df.iloc[:, 0]
        open_ = df["Open"] if "Open" in df.columns else close
        return pd.DataFrame({"Open": open_, "Close": close}).sort_index()
    s = data.sort_index()
    return pd.DataFrame({"Open": s, "Close": s}).sort_index()


def _price_frames(
    prices: Mapping[str, pd.Series],
    tickers: list[str],
    start: date,
    end: date,
    ohlc: Mapping[str, pd.DataFrame] | None = None,
    fx_rates: Mapping[str, pd.Series | pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    close_sources: dict[str, pd.Series] = {}
    open_sources: dict[str, pd.Series] = {}
    for t in tickers:
        frame = _as_ohlc_frame(ohlc[t]) if ohlc and t in ohlc else _as_ohlc_frame(prices[t])
        close_sources[t] = frame["Close"]
        open_sources[t] = frame["Open"]

    raw_close = pd.concat(close_sources, axis=1).sort_index()
    intraday = _has_intraday_index(raw_close.index)
    if intraday:
        timeline = raw_close.index
        if fx_rates:
            for rate_data in fx_rates.values():
                rate_frame = _fx_frame(rate_data)
                if _has_intraday_index(rate_frame.index):
                    timeline = timeline.union(rate_frame.index)
        close_df = raw_close.reindex(timeline.sort_values()).ffill().dropna(how="all")
    else:
        close_df = raw_close.ffill().dropna(how="all")
    close_df = _slice_indexed_frame(close_df, start, end)
    if close_df.empty:
        raise ValueError("No price data in [start, end] window")

    raw_open = pd.concat(open_sources, axis=1).sort_index()
    open_df = raw_open.reindex(close_df.index)
    return close_df, open_df


def _fx_frame(data: pd.Series | pd.DataFrame) -> pd.DataFrame:
    return _as_ohlc_frame(data)


def _action_values_on(series: pd.Series | None, when: pd.Timestamp) -> pd.Series:
    if series is None or series.empty or not isinstance(series.index, pd.DatetimeIndex):
        return pd.Series(dtype=float)
    normalized = series.dropna().sort_index().copy()
    if normalized.index.tz is not None:
        normalized.index = normalized.index.tz_localize(None)
    target = pd.Timestamp(when.date())
    return normalized[normalized.index.normalize() == target]


def _split_ratio_on(series: pd.Series | None, when: pd.Timestamp) -> float | None:
    values = _action_values_on(series, when)
    if values.empty:
        return None
    ratio = 1.0
    for value in values:
        if np.isfinite(float(value)) and float(value) > 0:
            ratio *= float(value)
    return ratio if ratio != 1.0 else None


def _dividend_amount_on(series: pd.Series | None, when: pd.Timestamp) -> float | None:
    values = _action_values_on(series, when)
    if values.empty:
        return None
    amount = float(values.sum())
    return amount if np.isfinite(amount) and amount > 0 else None


def _fx_intraday_components(
    data: pd.Series | pd.DataFrame,
) -> tuple[pd.Series, pd.Series | None, pd.Series | None]:
    if isinstance(data, pd.DataFrame):
        frame = data.sort_index()
        close = frame["Close"] if "Close" in frame.columns else frame.iloc[:, 0]
        bar_minutes = frame["_bar_minutes"] if "_bar_minutes" in frame.columns else None
        source = frame["_fx_source"] if "_fx_source" in frame.columns else None
        return close.dropna(), bar_minutes, source
    series = data.sort_index()
    return series.dropna(), None, None


def _default_bar_minutes(series: pd.Series, fallback: int = 5) -> int:
    interval = series.attrs.get("bar_minutes")
    if isinstance(interval, (int, float)) and interval > 0:
        return int(interval)
    if len(series.index) >= 2:
        deltas = pd.Series(series.index[1:] - series.index[:-1])
        median = deltas.median()
        if pd.notna(median) and median > pd.Timedelta(0):
            return max(1, int(pd.Timedelta(median).total_seconds() // 60))
    return fallback


def _normalize_fx_source(value) -> str:
    if isinstance(value, str) and value:
        return value
    return "minute_asof"


def _fx_rate(
    currency: str,
    when: pd.Timestamp,
    fx_rates: Mapping[str, pd.Series | pd.DataFrame] | None,
    column: str,
) -> float | None:
    if currency == "USD":
        return 1.0
    if not fx_rates or currency not in fx_rates:
        return None
    frame = _fx_frame(fx_rates[currency])
    if column not in frame.columns:
        column = "Close"
    series = frame[column].dropna().sort_index()
    if series.empty:
        return None
    available = series[series.index <= when]
    if available.empty:
        return None
    rate = float(available.iloc[-1])
    return rate if rate > 0 else None


def _fx_rate_with_asof(
    currency: str,
    when: pd.Timestamp,
    fx_rates: Mapping[str, pd.Series | pd.DataFrame] | None,
    column: str,
) -> tuple[float, date | datetime | None] | None:
    if currency == "USD":
        return 1.0, when.to_pydatetime() if when.time() != datetime.min.time() else when.date()
    if not fx_rates or currency not in fx_rates:
        return None
    frame = _fx_frame(fx_rates[currency])
    if column not in frame.columns:
        column = "Close"
    series = frame[column].dropna().sort_index()
    if series.empty:
        return None
    available = series[series.index <= when]
    if available.empty:
        return None
    rate = float(available.iloc[-1])
    if rate <= 0:
        return None
    as_of_ts = pd.Timestamp(available.index[-1])
    as_of = as_of_ts.to_pydatetime() if as_of_ts.time() != datetime.min.time() else as_of_ts.date()
    return rate, as_of


def _purchase_instant(
    ticker: str,
    when: pd.Timestamp,
    intraday: bool,
    timeline_tz: ZoneInfo | None,
) -> pd.Timestamp:
    market_tz = tz_of(market_of(ticker))
    ts = pd.Timestamp(when)
    if not intraday:
        return pd.Timestamp(
            datetime.combine(ts.date(), open_time_of(market_of(ticker))),
            tz=market_tz,
        )
    if ts.tzinfo is None:
        ts = ts.tz_localize(timeline_tz or market_tz)
    else:
        ts = ts.tz_convert(timeline_tz or market_tz)
    return ts.tz_convert(market_tz)


def _purchase_timestamp(
    ticker: str,
    when: pd.Timestamp,
    intraday: bool,
    timeline_tz: ZoneInfo | None,
) -> date | datetime:
    instant = _purchase_instant(ticker, when, intraday, timeline_tz)
    return instant.tz_localize(None).to_pydatetime()


def _intraday_fx_observation(
    currency: str,
    purchase_instant: pd.Timestamp,
    fx_intraday_rates: Mapping[str, pd.Series | pd.DataFrame] | None,
    timeline_tz: ZoneInfo | None = None,
) -> FxRateObservation | None:
    if currency == "USD":
        return FxRateObservation(
            rate=1.0,
            source="base_currency",
            as_of=purchase_instant.tz_localize(None).to_pydatetime(),
            note="USD base currency; no FX conversion.",
        )
    if not fx_intraday_rates or currency not in fx_intraday_rates:
        return None
    series, bar_minutes_data, source_data = _fx_intraday_components(fx_intraday_rates[currency])
    if series.empty or not isinstance(series.index, pd.DatetimeIndex):
        return None
    indexed = series.copy()
    if indexed.index.tz is None:
        if timeline_tz is not None:
            indexed.index = indexed.index.tz_localize(timeline_tz)
            target = purchase_instant.tz_convert(timeline_tz)
        else:
            target = purchase_instant.tz_localize(None)
    else:
        target = purchase_instant
        if target.tzinfo is None:
            target = target.tz_localize(ZoneInfo("UTC"))
        target = target.tz_convert(indexed.index.tz)

    if bar_minutes_data is not None:
        bar_minutes = bar_minutes_data.reindex(indexed.index).fillna(_default_bar_minutes(indexed))
    else:
        bar_minutes = pd.Series(_default_bar_minutes(indexed), index=indexed.index)
    bar_ends = pd.DatetimeIndex([
        pd.Timestamp(ts) + pd.Timedelta(minutes=int(minutes))
        for ts, minutes in bar_minutes.items()
    ])
    available_mask = bar_ends <= target
    available = indexed.loc[available_mask]
    if available.empty:
        return None
    rate = float(available.iloc[-1])
    if rate <= 0:
        return None
    as_of = pd.Timestamp(available.index[-1])
    source = (
        _normalize_fx_source(source_data.reindex(indexed.index).loc[available.index[-1]])
        if source_data is not None else _normalize_fx_source(indexed.attrs.get("fx_source"))
    )
    return FxRateObservation(
        rate=rate,
        source=source,
        as_of=as_of.to_pydatetime(),
        note=(
            None if source == "minute_asof"
            else "Using hourly FX data because minute-level history was unavailable."
        ),
    )


def _fx_observation_for_purchase(
    currency: str,
    ticker: str,
    when: pd.Timestamp,
    intraday: bool,
    fx_rates: Mapping[str, pd.Series | pd.DataFrame] | None,
    fx_intraday_rates: Mapping[str, pd.Series | pd.DataFrame] | None,
    timeline_tz: ZoneInfo | None,
) -> FxRateObservation | None:
    purchase_instant = _purchase_instant(ticker, when, intraday, timeline_tz)
    intraday_candidates = fx_intraday_rates if fx_intraday_rates is not None else (
        fx_rates if intraday else None
    )
    intraday_observation = _intraday_fx_observation(
        currency, purchase_instant, intraday_candidates, timeline_tz,
    )
    if intraday_observation is not None:
        return intraday_observation
    daily_when = pd.Timestamp(when.date())
    daily = _fx_rate_with_asof(currency, daily_when, fx_rates, "Open")
    if daily is None:
        return None
    rate, as_of = daily
    return FxRateObservation(
        rate=rate,
        source="daily_fallback",
        as_of=as_of,
        note=(
            "No intraday FX tick was available at or before the stock market "
            "open; using the FX daily Open as an approximation."
        ),
    )


def _purchase_event(
    ticker: str,
    when: pd.Timestamp,
    price: float,
    fx_observation: FxRateObservation,
    shares: float,
    total_shares: float,
    intraday: bool,
    timeline_tz: ZoneInfo | None,
) -> PurchaseEvent:
    market = market_of(ticker)
    timezone = getattr(tz_of(market), "key", str(tz_of(market)))
    currency = currency_of(ticker)
    return PurchaseEvent(
        ticker=ticker,
        market=market,
        timezone=timezone,
        purchased_at_timezone=timezone,
        purchased_at=_purchase_timestamp(ticker, when, intraday, timeline_tz),
        currency=currency,
        price=float(price),
        fx_rate=float(fx_observation.rate),
        fx_source=fx_observation.source,
        fx_as_of=fx_observation.as_of,
        fx_alignment_note=fx_observation.note,
        price_usd=float(price / fx_observation.rate),
        shares=float(shares),
        total_shares=float(total_shares),
    )


def _simulate(
    prices: Mapping[str, pd.Series],
    tickers: list[str],
    weights_for_date,
    plan: Plan,
    start: date,
    end: date,
    ohlc: Mapping[str, pd.DataFrame] | None = None,
    fx_rates: Mapping[str, pd.Series | pd.DataFrame] | None = None,
    fx_intraday_rates: Mapping[str, pd.Series | pd.DataFrame] | None = None,
    dividends: Mapping[str, pd.Series | None] | None = None,
    splits: Mapping[str, pd.Series | None] | None = None,
    timeline_tz: ZoneInfo | None = None,
) -> BacktestResult:
    close_df, open_df = _price_frames(prices, tickers, start, end, ohlc, fx_rates)
    trading_days = close_df.index
    intraday = _has_intraday_index(trading_days)
    if intraday:
        invest_dates = [trading_days[0]]
    else:
        invest_dates = _frequency_to_invest_dates(start, end, plan.frequency, trading_days)
    invest_set = set(invest_dates)

    shares = {t: 0.0 for t in tickers}
    nav_history: list[float] = []
    cash_history: list[float] = []
    cumulative_cash = 0.0
    cash_left_usd = 0.0
    intraday_cash_seeded = False
    intraday_attempted: set[str] = set()
    purchase_events: list[PurchaseEvent] = []

    for d in trading_days:
        if not intraday:
            for t in tickers:
                ratio = _split_ratio_on(splits.get(t) if splits else None, d)
                if ratio is not None and shares[t] > 0:
                    shares[t] *= ratio
            for t in tickers:
                amount = _dividend_amount_on(dividends.get(t) if dividends else None, d)
                if amount is None or shares[t] <= 0:
                    continue
                fx_div = _fx_rate(currency_of(t), d, fx_rates, "Close")
                if fx_div is None:
                    continue
                cash_left_usd += shares[t] * amount / fx_div

        if intraday:
            if not intraday_cash_seeded:
                cumulative_cash += plan.amount
                cash_left_usd += plan.amount
                intraday_cash_seeded = True
            weights = weights_for_date(d)
            for t, w in weights.items():
                if t in intraday_attempted:
                    continue
                px = float(open_df.at[d, t])
                if not np.isfinite(px) or px <= 0:
                    continue
                currency = currency_of(t)
                fx_open = _fx_observation_for_purchase(
                    currency, t, d, intraday, fx_rates, fx_intraday_rates, timeline_tz,
                )
                if fx_open is None:
                    continue
                unit_cost_usd = px * lot_size(t) / fx_open.rate
                if unit_cost_usd <= 0:
                    intraday_attempted.add(t)
                    continue
                budget = min(plan.amount * float(w), cash_left_usd)
                buyable_lots = floor((budget + 1e-9) / unit_cost_usd)
                if buyable_lots > 0:
                    delta_shares = float(buyable_lots * lot_size(t))
                    spent_usd = delta_shares * px / fx_open.rate
                    shares[t] += delta_shares
                    cash_left_usd = max(0.0, cash_left_usd - spent_usd)
                    purchase_events.append(
                        _purchase_event(
                            t, d, px, fx_open, delta_shares, shares[t],
                            intraday, timeline_tz,
                        )
                    )
                intraday_attempted.add(t)
        elif d in invest_set:
            weights = weights_for_date(d)
            cumulative_cash += plan.amount
            cash_left_usd += plan.amount
            available_at_rebalance = cash_left_usd

            for t, w in weights.items():
                px = float(open_df.at[d, t])
                if not np.isfinite(px) or px <= 0:
                    continue
                currency = currency_of(t)
                fx_open = _fx_observation_for_purchase(
                    currency, t, d, intraday, fx_rates, fx_intraday_rates, timeline_tz,
                )
                if fx_open is None:
                    continue
                unit_cost_usd = px * lot_size(t) / fx_open.rate
                if unit_cost_usd <= 0:
                    continue
                budget = min(available_at_rebalance * float(w), cash_left_usd)
                buyable_lots = floor((budget + 1e-9) / unit_cost_usd)
                if buyable_lots <= 0:
                    continue
                delta_shares = float(buyable_lots * lot_size(t))
                spent_usd = delta_shares * px / fx_open.rate
                shares[t] += delta_shares
                cash_left_usd = max(0.0, cash_left_usd - spent_usd)
                purchase_events.append(
                    _purchase_event(
                        t, d, px, fx_open, delta_shares, shares[t],
                        intraday, timeline_tz,
                    )
                )

        asset_nav = 0.0
        for t in tickers:
            px = float(close_df.at[d, t])
            if not np.isfinite(px) or px <= 0:
                continue
            fx_close = _fx_rate(currency_of(t), d, fx_rates, "Close")
            if fx_close is None:
                continue
            asset_nav += shares[t] * px / fx_close

        nav_history.append(asset_nav + cash_left_usd)
        cash_history.append(cumulative_cash)

    nav_arr = np.array(nav_history)
    cash_arr = np.array(cash_history)
    return_pct = np.zeros_like(nav_arr)
    nonzero = cash_arr > 0
    return_pct[nonzero] = nav_arr[nonzero] / cash_arr[nonzero] - 1.0

    final_nav = float(nav_arr[-1])
    total_invested = float(cash_arr[-1])
    cumulative_return = (final_nav - total_invested) / total_invested if total_invested > 0 else 0.0

    cash_flows = [-plan.amount for _ in invest_dates] + [final_nav]
    cf_dates = list(invest_dates) + [trading_days[-1]]
    base_date = cf_dates[0]
    day_offsets = [(d - base_date).days for d in cf_dates]
    irr = _irr(cash_flows, day_offsets)
    annualized = float(irr) if irr is not None else cumulative_return

    mdd = _max_drawdown(np.where(cash_arr > 0, return_pct + 1.0, 1.0))

    per_asset_final = {}
    last_day = trading_days[-1]
    for t in tickers:
        fx_close = _fx_rate(currency_of(t), last_day, fx_rates, "Close")
        if fx_close is None:
            continue
        px = float(close_df.at[last_day, t])
        if not np.isfinite(px) or px <= 0:
            continue
        per_asset_final[t] = float(shares[t] * px / fx_close)

    return BacktestResult(
        dates=list(trading_days),
        nav=nav_history,
        cash_invested=cash_history,
        return_pct=return_pct.tolist(),
        invest_dates=invest_dates,
        final_nav=final_nav,
        total_invested=total_invested,
        cumulative_return=cumulative_return,
        annualized_return=annualized,
        max_drawdown=mdd,
        per_asset_final_value=per_asset_final,
        cash_left={"USD": float(cash_left_usd)},
        purchase_events=purchase_events,
    )


def backtest(
    prices: Mapping[str, pd.Series],
    weights: Mapping[str, float],
    plan: Plan,
    start: date,
    end: date,
    ohlc: Mapping[str, pd.DataFrame] | None = None,
    fx_rates: Mapping[str, pd.Series | pd.DataFrame] | None = None,
    fx_intraday_rates: Mapping[str, pd.Series | pd.DataFrame] | None = None,
    dividends: Mapping[str, pd.Series | None] | None = None,
    splits: Mapping[str, pd.Series | None] | None = None,
    timeline_tz: ZoneInfo | None = None,
) -> BacktestResult:
    """Simulate dollar-cost-averaging into a weighted portfolio.

    Uses auto-adjusted close prices, which already encode dividend
    reinvestment, so DRIP is implicit: buying ``money / adj_price[t]``
    shares accumulates the same total return a real DRIP investor would
    see, without having to track ex-dates separately.
    """
    if plan.amount <= 0:
        raise ValueError("plan.amount must be > 0")
    if not weights:
        raise ValueError("weights must be non-empty")
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 1e-6:
        raise ValueError(f"weights must sum to 1, got {weight_sum:.6f}")
    missing = [t for t in weights if t not in prices]
    if missing:
        raise ValueError(f"missing price series for tickers: {missing}")

    tickers = list(weights)
    return _simulate(
        prices,
        tickers,
        lambda _d: weights,
        plan,
        start,
        end,
        ohlc=ohlc,
        fx_rates=fx_rates,
        fx_intraday_rates=fx_intraday_rates,
        dividends=dividends,
        splits=splits,
        timeline_tz=timeline_tz,
    )


def rolling_weight_backtest(
    prices: Mapping[str, pd.Series],
    scheduled_weights: (
        Mapping[int, Mapping[str, float]]
        | Sequence[tuple[date, date, Mapping[str, float]]]
    ),
    plan: Plan,
    start: date,
    end: date,
    ohlc: Mapping[str, pd.DataFrame] | None = None,
    fx_rates: Mapping[str, pd.Series | pd.DataFrame] | None = None,
    fx_intraday_rates: Mapping[str, pd.Series | pd.DataFrame] | None = None,
    dividends: Mapping[str, pd.Series | None] | None = None,
    splits: Mapping[str, pd.Series | None] | None = None,
    timeline_tz: ZoneInfo | None = None,
) -> BacktestResult:
    """DCA backtest where new cash uses the active scheduled weights.

    Existing shares are not sold/rebalanced when the active schedule changes.
    For backwards compatibility, callers may pass a ``year -> weights`` mapping;
    newer rolling-allocation flows pass explicit effective date ranges.
    """
    if plan.amount <= 0:
        raise ValueError("plan.amount must be > 0")
    if not scheduled_weights:
        raise ValueError("scheduled_weights must be non-empty")

    if isinstance(scheduled_weights, Mapping):
        schedule_entries = [
            (
                pd.Timestamp(date(year, 1, 1)),
                pd.Timestamp(date(year, 12, 31)),
                weights,
                f"year {year}",
            )
            for year, weights in scheduled_weights.items()
        ]
    else:
        schedule_entries = [
            (
                pd.Timestamp(effective_start),
                pd.Timestamp(effective_end),
                weights,
                f"{effective_start} to {effective_end}",
            )
            for effective_start, effective_end, weights in scheduled_weights
        ]

    if not schedule_entries:
        raise ValueError("scheduled_weights must be non-empty")

    tickers = sorted({
        t
        for _start, _end, weights, _label in schedule_entries
        for t in weights
    })
    missing = [t for t in tickers if t not in prices]
    if missing:
        raise ValueError(f"missing price series for tickers: {missing}")

    for effective_start, effective_end, weights, label in schedule_entries:
        if effective_start > effective_end:
            raise ValueError(f"schedule {label} has start after end")
        if not weights:
            raise ValueError(f"schedule {label} weights are empty")
        weight_sum = sum(weights.values())
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError(
                f"schedule {label} weights must sum to 1, got {weight_sum:.6f}"
            )

    def weights_for_date(d: pd.Timestamp) -> Mapping[str, float]:
        current = pd.Timestamp(d.date())
        for effective_start, effective_end, weights, _label in schedule_entries:
            if effective_start <= current <= effective_end:
                return weights
        raise ValueError(f"missing weights for execution date {current.date()}")

    return _simulate(
        prices,
        tickers,
        weights_for_date,
        plan,
        start,
        end,
        ohlc=ohlc,
        fx_rates=fx_rates,
        fx_intraday_rates=fx_intraday_rates,
        dividends=dividends,
        splits=splits,
        timeline_tz=timeline_tz,
    )
