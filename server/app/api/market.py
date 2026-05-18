from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import isfinite
from numbers import Real
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from fastapi import APIRouter, Depends, HTTPException, Query

from app.data.base import DataSource, DataSourceError
from app.data.market_hours import close_time_of, market_status, ref_trading_day, tz_of
from app.data.symbols import currency_of, market_of
from app.deps import get_data_source
from app.schemas import (
    RANGE_DAYS,
    AssetInfo,
    AssetSeries,
    DividendPoint,
    IntradayPoint,
    IntradaySeries,
    KlinePeriod,
    OHLCPoint,
    PricePoint,
    Range,
    SeriesNotice,
)
from app.services.display_quote import display_quote

router = APIRouter()
FULL_HISTORY_START = date(1900, 1, 1)
FX_HISTORY_START = date(1970, 1, 1)
FX_TRADING_TZ = ZoneInfo("America/New_York")
FX_TRADING_DAY_CUTOFF = time(17, 0)
FX_DAILY_SOURCE_LABEL = "Yahoo日线OHLC"
FX_SOURCE_LABEL_COL = "_fx_source_label"
FX_SOURCE_RANK_COL = "_fx_source_rank"
FX_INTRADAY_KLINE_SOURCES = (
    ("7d", "1m", "1分钟分时聚合"),
    ("60d", "5m", "5分钟分时聚合"),
    ("2y", "1h", "1小时分时聚合"),
)
FX_DISPLAY_SYMBOL_FALLBACKS = {
    "USDCNH=X": ("USDCNH=X", "CNH=X"),
}


def _user_tz(tz_name: str | None) -> ZoneInfo:
    if not tz_name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _tz_name(tz: ZoneInfo) -> str:
    return getattr(tz, "key", str(tz))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _market_local_index(index: pd.DatetimeIndex, market: str) -> pd.DatetimeIndex:
    if index.tz is None:
        try:
            return index.tz_localize(tz_of(market), ambiguous="infer", nonexistent="shift_forward")
        except Exception:
            return index.tz_localize(tz_of(market), ambiguous=False, nonexistent="shift_forward")
    return index.tz_convert(tz_of(market))


def _interval_delta(interval: str) -> pd.Timedelta:
    unit = interval[-1].lower()
    try:
        value = int(interval[:-1])
    except ValueError:
        return pd.Timedelta(minutes=5)
    if unit == "m":
        return pd.Timedelta(minutes=value)
    if unit == "h":
        return pd.Timedelta(hours=value)
    return pd.Timedelta(minutes=5)


def _label_closed_market_final_bar(
    series: pd.Series,
    local_index: pd.DatetimeIndex,
    market: str,
    selected_day: date,
    user_tz: ZoneInfo,
    interval: str,
    status: str | None,
) -> pd.Series:
    if series.empty or status != "closed":
        return series
    close_local = pd.Timestamp(
        datetime.combine(selected_day, close_time_of(market)),
        tz=tz_of(market),
    )
    last_local = local_index[-1]
    delta = close_local - last_local
    tolerance = max(_interval_delta(interval), pd.Timedelta(minutes=5))
    if pd.Timedelta(0) < delta <= tolerance:
        target = close_local.tz_convert(user_tz).tz_localize(None)
        if target not in series.index:
            out = series.copy()
            new_index = list(out.index)
            new_index[-1] = target
            out.index = pd.DatetimeIndex(new_index)
            return out.sort_index()
    return series


def _intraday_for_today(
    series: pd.Series,
    market: str,
    ref_day: date,
    user_tz: ZoneInfo,
    interval: str,
    status: str | None,
) -> tuple[pd.Series, date]:
    if series.empty or not isinstance(series.index, pd.DatetimeIndex):
        return series.sort_index(), ref_day
    sorted_series = series.sort_index()
    local_index = _market_local_index(sorted_series.index, market)
    available_days = sorted({ts.date() for ts in local_index if ts.date() <= ref_day})
    if not available_days:
        available_days = sorted({ts.date() for ts in local_index})
        if not available_days:
            return sorted_series.iloc[0:0], ref_day
    selected_day = ref_day if ref_day in available_days else available_days[-1]
    mask = [ts.date() == selected_day for ts in local_index]
    selected = sorted_series.loc[mask]
    selected_index = local_index[mask]
    out = selected.copy()
    out.index = selected_index.tz_convert(user_tz).tz_localize(None)
    out = _label_closed_market_final_bar(
        out, selected_index, market, selected_day, user_tz, interval, status,
    )
    return out.sort_index(), selected_day


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
    value = float(close.iloc[-1])
    return value if value > 0 else None


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
    value = float(close.iloc[-1])
    return value if value > 0 else None


def _finite_positive(value) -> float | None:
    if isinstance(value, Real) and isfinite(float(value)) and float(value) > 0:
        return float(value)
    return None


def _display_time(value, display_tz: ZoneInfo) -> pd.Timestamp | None:
    if not isinstance(value, datetime):
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    return ts.tz_convert(display_tz).tz_localize(None)


def _series_to_display_tz(series: pd.Series, display_tz: ZoneInfo) -> pd.Series:
    if series.empty or not isinstance(series.index, pd.DatetimeIndex):
        return series.sort_index()
    out = series.sort_index().copy()
    if out.index.tz is None:
        out.index = out.index.tz_localize(timezone.utc)
    out.index = out.index.tz_convert(display_tz).tz_localize(None)
    return out.sort_index()


def _apply_latest_point(
    prices: pd.Series,
    latest: float | None,
    as_of: datetime | None,
    display_tz: ZoneInfo,
    ref_day: date | None,
    status: str | None,
) -> pd.Series:
    if latest is None or prices.empty:
        return prices
    out = prices.sort_index().copy()
    target = _display_time(as_of, display_tz)
    if (
        status != "closed"
        and target is not None
        and (ref_day is None or target.date() == ref_day)
        and target > out.index[-1]
    ):
        out.loc[target] = latest
        return out.sort_index()
    out.iloc[-1] = latest
    return out


def _quote_outside_intraday_bounds(
    quote_target: pd.Timestamp | None,
    prices: pd.Series,
    interval: str,
    reject_after_last: bool,
) -> bool:
    if quote_target is None or prices.empty:
        return False
    last_ts = prices.sort_index().index[-1]
    tolerance = max(_interval_delta(interval) * 2, pd.Timedelta(minutes=5))
    if quote_target < last_ts - tolerance:
        return True
    if reject_after_last and quote_target > last_ts + tolerance:
        return True
    return False


def _align_fx_quote_to_intraday_window(
    quote_last: float | None,
    quote_target: pd.Timestamp | None,
    prices: pd.Series,
    interval: str,
) -> tuple[float | None, pd.Series]:
    if quote_last is None or quote_target is None or prices.empty:
        return quote_last, prices.sort_index()

    ordered = prices.sort_index().copy()
    first_ts = ordered.index[0]
    last_ts = ordered.index[-1]
    tolerance = max(_interval_delta(interval) * 2, pd.Timedelta(minutes=5))
    if quote_target < first_ts - tolerance or quote_target > last_ts + tolerance:
        return None, ordered

    if quote_target <= last_ts:
        ordered = ordered.loc[ordered.index <= quote_target].copy()
        ordered.loc[quote_target] = quote_last
        return quote_last, ordered.sort_index()

    return quote_last, ordered


def _intraday_quote(
    src: DataSource,
    symbol: str,
    prices: pd.Series,
    ref_day: date | None,
    market: str,
    display_tz: ZoneInfo,
    status: str | None,
    interval: str,
    reject_quote_after_last: bool = False,
    prefer_quote_within_window: bool = False,
) -> tuple[dict | None, pd.Series]:
    raw = src.get_quote(symbol) or {}
    as_of = raw.get("as_of")
    quote_last = _finite_positive(raw.get("last_price"))
    sorted_prices = prices.sort_index()
    intraday_last = (
        float(sorted_prices.iloc[-1])
        if not sorted_prices.empty and float(sorted_prices.iloc[-1]) > 0 else None
    )
    quote_target = _display_time(as_of, display_tz)
    if prefer_quote_within_window:
        quote_last, sorted_prices = _align_fx_quote_to_intraday_window(
            quote_last, quote_target, sorted_prices, interval,
        )
    elif (
        quote_last is not None
        and quote_target is not None
        and not sorted_prices.empty
        and _quote_outside_intraday_bounds(
            quote_target, sorted_prices, interval, reject_quote_after_last,
        )
    ):
        quote_last = None

    daily_close = None
    if ref_day is not None and status == "closed":
        daily_close = _daily_close_on(src, symbol, ref_day, fresh=True)
    if status == "closed":
        last_price = daily_close or quote_last or intraday_last
        source = (
            "daily_close" if daily_close is not None
            else "quote_snapshot" if quote_last is not None
            else "intraday_fallback"
        )
    else:
        last_price = quote_last or intraday_last
        source = "quote_snapshot" if quote_last is not None else "intraday_fallback"

    if last_price is not None:
        latest_as_of = as_of if source == "quote_snapshot" else None
        sorted_prices = _apply_latest_point(
            sorted_prices, last_price, latest_as_of, display_tz, ref_day, status,
        )
        if sorted_prices.empty:
            pass
        elif source != "quote_snapshot":
            last_ts = sorted_prices.index[-1]
            if hasattr(last_ts, "to_pydatetime"):
                as_of = last_ts.to_pydatetime()

    previous_close = raw.get("previous_close")
    if ref_day is not None:
        previous_close = _previous_close_before(src, symbol, ref_day) or previous_close

    change_pct = None
    if last_price is not None and previous_close is not None and previous_close > 0:
        change_pct = last_price / previous_close - 1.0
    else:
        change_pct = raw.get("change_pct")

    if last_price is None and previous_close is None:
        return None, sorted_prices
    return {
        "last_price": last_price,
        "previous_close": previous_close,
        "change_pct": change_pct,
        "as_of": as_of,
        "source": source,
    }, sorted_prices


def _range_end(end: date, range_str: str) -> date:
    return end


def _range_start(end: date, range_str: str) -> date:
    if range_str == "today":
        return end
    if range_str == "ytd":
        return date(end.year, 1, 1)
    return end - timedelta(days=RANGE_DAYS[range_str])


def _build_asset_series(
    src: DataSource,
    symbol: str,
    range_str: str,
    include_dividends: bool,
    include_ohlc: bool = False,
    intraday: bool = False,
    user_tz_name: str | None = None,
) -> AssetSeries:
    if range_str not in RANGE_DAYS and range_str not in {"today", "ytd"}:
        raise HTTPException(400, f"unknown range: {range_str}")
    if range_str == "today":
        intraday = _build_intraday_series(
            src, symbol, period="5d", interval="1m", user_tz_name=user_tz_name,
        )
        ohlc = None
        if include_ohlc:
            ohlc = _today_ohlc_points(
                src, symbol, intraday.ref_day, intraday.market_status,
                tz_of(market_of(symbol)),
                interval="1m",
            )
        return AssetSeries(
            symbol=symbol,
            range=range_str,
            points=[
                PricePoint(date=p.datetime, close=p.close)
                for p in intraday.points
            ],
            ohlc=ohlc,
            dividends=None,
            market_status=intraday.market_status,
            ref_day=intraday.ref_day,
            market=intraday.market,
            currency=intraday.currency,
            display_timezone=intraday.display_timezone,
            quote=intraday.quote,
        )
    if range_str == "7d" and intraday:
        return _build_multiday_intraday_asset_series(
            src, symbol, range_str, include_dividends=include_dividends,
            include_ohlc=include_ohlc, display_tz=tz_of(market_of(symbol)),
            include_quote=True,
        )

    end = _range_end(date.today(), range_str)
    start = _range_start(end, range_str)
    df_ohlc = None
    try:
        df_ohlc = src.get_ohlc(symbol, start, end)
        prices = df_ohlc["Close"].dropna()
    except DataSourceError as e:
        try:
            prices = src.get_prices(symbol, start, end)
        except DataSourceError:
            raise HTTPException(404, str(e))

    points = [
        PricePoint(
            date=ts.date(),
            close=float(v),
            open=(
                float(df_ohlc.at[ts, "Open"])
                if df_ohlc is not None and ts in df_ohlc.index and "Open" in df_ohlc.columns
                else None
            ),
        )
        for ts, v in prices.items()
    ]

    ohlc = None
    if include_ohlc:
        try:
            df = df_ohlc if df_ohlc is not None else src.get_ohlc(symbol, start, end)
            ohlc = [
                OHLCPoint(
                    date=ts.date(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]) if "Volume" in row and row["Volume"] == row["Volume"] else None,
                )
                for ts, row in df.iterrows()
            ]
        except DataSourceError:
            ohlc = None

    dividends = None
    if include_dividends:
        d = src.get_dividends(symbol, start, end)
        if d is not None:
            dividends = [
                DividendPoint(date=ts.date(), amount=float(v))
                for ts, v in d.items()
            ]

    return AssetSeries(
        symbol=symbol, range=range_str,
        points=points, ohlc=ohlc, dividends=dividends,
        quote=display_quote(src, symbol, now=_now_utc()),
    )


def _intraday_period_for_range(range_str: str) -> str:
    if range_str == "7d":
        return "7d"
    return "1d"


def _intraday_frame_with_fallback(
    src: DataSource,
    symbol: str,
    period: str,
) -> tuple[pd.DataFrame, str]:
    errors: list[str] = []
    for interval in ("1m", "5m"):
        try:
            return src.get_intraday_ohlc_tz(symbol, period=period, interval=interval), interval
        except DataSourceError as exc:
            errors.append(str(exc))
    detail = errors[-1] if errors else f"No intraday data for {symbol}"
    raise HTTPException(404, detail)


def _intraday_points_from_frame(
    frame: pd.DataFrame,
    display_tz: ZoneInfo,
) -> pd.DataFrame:
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return frame.sort_index()
    out = frame.sort_index().copy()
    if out.index.tz is None:
        out.index = out.index.tz_localize(timezone.utc)
    out.index = out.index.tz_convert(display_tz).tz_localize(None)
    return out.sort_index()


def _build_multiday_intraday_asset_series(
    src: DataSource,
    symbol: str,
    range_str: str,
    include_dividends: bool,
    include_ohlc: bool,
    display_tz: ZoneInfo,
    include_quote: bool,
    is_fx: bool = False,
) -> AssetSeries:
    period = _intraday_period_for_range(range_str)
    try:
        frame, interval = _intraday_frame_with_fallback(src, symbol, period)
    except HTTPException:
        return _build_asset_series(
            src, symbol, range_str, include_dividends=include_dividends,
            include_ohlc=include_ohlc, intraday=False,
        )
    frame = _intraday_points_from_frame(frame, display_tz)
    if frame.empty or "Close" not in frame.columns:
        return _build_asset_series(
            src, symbol, range_str, include_dividends=include_dividends,
            include_ohlc=include_ohlc, intraday=False,
        )

    clean = frame.dropna(subset=["Close"]).sort_index()
    if clean.empty:
        return _build_asset_series(
            src, symbol, range_str, include_dividends=include_dividends,
            include_ohlc=include_ohlc, intraday=False,
        )

    quote = None
    close_for_points = clean["Close"].dropna()
    if include_quote and is_fx:
        quote, close_for_points = _intraday_quote(
            src, symbol, close_for_points, None, market_of(symbol), display_tz,
            None, interval, reject_quote_after_last=True,
            prefer_quote_within_window=True,
        )
    clean_for_ohlc = clean
    if is_fx and not close_for_points.empty:
        clean_for_ohlc = clean.loc[clean.index <= close_for_points.sort_index().index[-1]]

    points = [
        PricePoint(
            date=ts.to_pydatetime(),
            close=float(close),
            open=(
                float(clean.at[ts, "Open"])
                if ts in clean.index and "Open" in clean.columns and pd.notna(clean.at[ts, "Open"])
                else None
            ),
        )
        for ts, close in close_for_points.sort_index().items()
    ]
    ohlc = _ohlc_points_from_frame(clean_for_ohlc) if include_ohlc else None

    dividends = None
    if include_dividends:
        start = clean.index[0].date()
        end = clean.index[-1].date()
        d = src.get_dividends(symbol, start, end)
        if d is not None:
            dividends = [
                DividendPoint(date=ts.date(), amount=float(v))
                for ts, v in d.items()
            ]

    return AssetSeries(
        symbol=symbol,
        range=range_str,
        points=points,
        ohlc=ohlc,
        dividends=dividends,
        market=market_of(symbol),
        currency=currency_of(symbol),
        display_timezone=_tz_name(display_tz),
        quote=quote if is_fx else (
            display_quote(src, symbol, now=_now_utc()) if include_quote else None
        ),
    )


def _label_closed_market_final_frame(
    frame: pd.DataFrame,
    local_index: pd.DatetimeIndex,
    market: str,
    selected_day: date,
    user_tz: ZoneInfo,
    interval: str,
    status: str | None,
) -> pd.DataFrame:
    if frame.empty or status != "closed":
        return frame
    close_local = pd.Timestamp(
        datetime.combine(selected_day, close_time_of(market)),
        tz=tz_of(market),
    )
    last_local = local_index[-1]
    delta = close_local - last_local
    tolerance = max(_interval_delta(interval), pd.Timedelta(minutes=5))
    if pd.Timedelta(0) < delta <= tolerance:
        target = close_local.tz_convert(user_tz).tz_localize(None)
        if target not in frame.index:
            out = frame.copy()
            new_index = list(out.index)
            new_index[-1] = target
            out.index = pd.DatetimeIndex(new_index)
            return out.sort_index()
    return frame


def _intraday_ohlc_for_today(
    frame: pd.DataFrame,
    market: str,
    ref_day: date,
    user_tz: ZoneInfo,
    interval: str,
    status: str | None,
) -> tuple[pd.DataFrame, date]:
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return frame.sort_index(), ref_day
    sorted_frame = frame.sort_index()
    local_index = _market_local_index(sorted_frame.index, market)
    available_days = sorted({ts.date() for ts in local_index if ts.date() <= ref_day})
    if not available_days:
        available_days = sorted({ts.date() for ts in local_index})
        if not available_days:
            return sorted_frame.iloc[0:0], ref_day
    selected_day = ref_day if ref_day in available_days else available_days[-1]
    mask = [ts.date() == selected_day for ts in local_index]
    selected = sorted_frame.loc[mask].copy()
    selected_index = local_index[mask]
    selected.index = selected_index.tz_convert(user_tz).tz_localize(None)
    selected = _label_closed_market_final_frame(
        selected, selected_index, market, selected_day, user_tz, interval, status,
    )
    return selected.sort_index(), selected_day


def _ohlc_points_from_frame(
    frame: pd.DataFrame,
    labels: dict[pd.Timestamp, tuple[date, date, str]] | None = None,
) -> list[OHLCPoint]:
    out: list[OHLCPoint] = []
    for ts, row in frame.sort_index().iterrows():
        stamp = pd.Timestamp(ts)
        value_date = (
            stamp.to_pydatetime()
            if stamp.time() != pd.Timestamp(stamp.date()).time()
            else stamp.date()
        )
        day = stamp.date()
        period_start, period_end, label = (
            labels.get(stamp, (day, day, str(value_date).replace(" ", "T")))
            if labels is not None else (day, day, str(value_date).replace(" ", "T"))
        )
        out.append(OHLCPoint(
            date=value_date,
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=(
                float(row["Volume"])
                if "Volume" in row and pd.notna(row["Volume"]) else None
            ),
            period_start=period_start,
            period_end=period_end,
            label=label,
        ))
    return out


def _today_ohlc_points(
    src: DataSource,
    symbol: str,
    ref_day: date | None,
    status: str | None,
    display_tz: ZoneInfo,
    interval: str,
) -> list[OHLCPoint] | None:
    if ref_day is None:
        return None
    market = market_of(symbol)
    try:
        frame = src.get_intraday_ohlc_tz(symbol, period="5d", interval=interval)
    except DataSourceError:
        return None
    selected, _selected_day = _intraday_ohlc_for_today(
        frame, market, ref_day, display_tz, interval, status,
    )
    if selected.empty:
        return None
    return _ohlc_points_from_frame(selected)


def _period_label(period: pd.Period, period_key: KlinePeriod) -> str:
    if period_key == "year":
        return str(period.year)
    if period_key == "quarter":
        return f"{period.year} Q{period.quarter}"
    return str(period.start_time.date())


def _aggregate_ohlc_frame(
    frame: pd.DataFrame,
    period_key: KlinePeriod,
) -> tuple[pd.DataFrame, dict[pd.Timestamp, tuple[date, date, str]]]:
    required = ["Open", "High", "Low", "Close"]
    clean = frame.sort_index().dropna(subset=required)
    if clean.empty:
        return clean, {}
    if period_key == "day":
        labels = {
            pd.Timestamp(ts): (pd.Timestamp(ts).date(), pd.Timestamp(ts).date(),
                               pd.Timestamp(ts).date().isoformat())
            for ts in clean.index
        }
        return clean, labels

    freq = "Q" if period_key == "quarter" else "Y"
    grouped = clean.groupby(clean.index.to_period(freq))
    rows = []
    labels: dict[pd.Timestamp, tuple[date, date, str]] = {}
    for period, group in grouped:
        if group.empty:
            continue
        ts = pd.Timestamp(group.index[-1])
        volume = (
            float(group["Volume"].sum())
            if "Volume" in group.columns and group["Volume"].notna().any() else None
        )
        rows.append((
            ts,
            {
                "Open": float(group["Open"].iloc[0]),
                "High": float(group["High"].max()),
                "Low": float(group["Low"].min()),
                "Close": float(group["Close"].iloc[-1]),
                "Volume": volume,
            },
        ))
        labels[ts] = (
            pd.Timestamp(period.start_time).date(),
            ts.date(),
            _period_label(period, period_key),
        )
    if not rows:
        return clean.iloc[0:0], {}
    out = pd.DataFrame([row for _ts, row in rows], index=pd.DatetimeIndex([ts for ts, _row in rows]))
    return out.sort_index(), labels


def _fx_history_start(end: date) -> date:
    return max(FX_HISTORY_START, end - timedelta(days=365 * 99))


def _filter_fx_ohlc_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return frame
    return frame[frame.index.dayofweek < 5].sort_index()


def _fx_data_symbols(symbol: str) -> tuple[str, ...]:
    return FX_DISPLAY_SYMBOL_FALLBACKS.get(symbol.upper(), (symbol,))


def _normalize_daily_ohlc_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return frame.sort_index()
    out = frame.sort_index().copy()
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out.index = out.index.normalize()
    return out[~out.index.duplicated(keep="last")].sort_index()


def _normalize_intraday_ohlc_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return frame.sort_index()
    out = frame.sort_index().copy()
    if out.index.tz is None:
        out.index = out.index.tz_localize(timezone.utc)
    return out.sort_index()


def _fetch_fx_daily_ohlc_with_fallback(
    src: DataSource,
    symbol: str,
    start: date,
    end: date,
) -> tuple[pd.DataFrame, str]:
    first_frame: tuple[pd.DataFrame, str] | None = None
    errors: list[str] = []
    for data_symbol in _fx_data_symbols(symbol):
        try:
            frame = src.get_ohlc(data_symbol, start, end)
        except DataSourceError as exc:
            errors.append(str(exc))
            continue
        clean = _filter_fx_ohlc_frame(_normalize_daily_ohlc_frame(frame))
        if clean.empty:
            continue
        if first_frame is None:
            first_frame = (clean, data_symbol)
        if len(clean) > 1:
            return clean, data_symbol
    if first_frame is not None:
        return first_frame
    detail = errors[-1] if errors else f"No OHLC data for {symbol}"
    raise HTTPException(404, detail)


def _fetch_fx_intraday_ohlc_with_fallback(
    src: DataSource,
    symbol: str,
) -> tuple[pd.DataFrame, str] | None:
    for data_symbol in _fx_data_symbols(symbol):
        frames: list[pd.DataFrame] = []
        for rank, (period, interval, source_label) in enumerate(FX_INTRADAY_KLINE_SOURCES):
            try:
                frame = src.get_intraday_ohlc_tz(data_symbol, period=period, interval=interval)
            except DataSourceError:
                continue
            clean = _normalize_intraday_ohlc_frame(frame)
            if not clean.empty:
                clean = clean.copy()
                clean[FX_SOURCE_LABEL_COL] = source_label
                clean[FX_SOURCE_RANK_COL] = rank
                frames.append(clean)
        if frames:
            combined = pd.concat(frames)
            combined = combined[~combined.index.duplicated(keep="first")]
            return combined.sort_index(), data_symbol
    return None


def _fx_trading_day(ts: pd.Timestamp) -> date:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(timezone.utc)
    local = stamp.tz_convert(FX_TRADING_TZ)
    day = local.date()
    if local.time() >= FX_TRADING_DAY_CUTOFF:
        day += timedelta(days=1)
    return day


def _aggregate_fx_intraday_daily_ohlc(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[pd.Timestamp, tuple[date, date, str]]]:
    required = ["Open", "High", "Low", "Close"]
    clean = frame.sort_index().dropna(subset=required)
    if clean.empty:
        return clean, {}

    rows = []
    labels: dict[pd.Timestamp, tuple[date, date, str]] = {}
    trading_days = [_fx_trading_day(pd.Timestamp(ts)) for ts in clean.index]
    for trading_day, group in clean.groupby(trading_days):
        if trading_day.weekday() >= 5 or group.empty:
            continue
        ts = pd.Timestamp(trading_day)
        volume = (
            float(group["Volume"].sum())
            if "Volume" in group.columns and group["Volume"].notna().any() else None
        )
        row = {
            "Open": float(group["Open"].iloc[0]),
            "High": float(group["High"].max()),
            "Low": float(group["Low"].min()),
            "Close": float(group["Close"].iloc[-1]),
            "Volume": volume,
        }
        if FX_SOURCE_RANK_COL in group.columns and FX_SOURCE_LABEL_COL in group.columns:
            rank = int(group[FX_SOURCE_RANK_COL].min())
            label_rows = group[group[FX_SOURCE_RANK_COL] == rank]
            label = str(label_rows[FX_SOURCE_LABEL_COL].iloc[0])
            row[FX_SOURCE_LABEL_COL] = label
            row[FX_SOURCE_RANK_COL] = rank
        rows.append((ts, row))
        labels[ts] = (trading_day, trading_day, trading_day.isoformat())

    if not rows:
        return clean.iloc[0:0], {}
    out = pd.DataFrame(
        [row for _ts, row in rows],
        index=pd.DatetimeIndex([ts for ts, _row in rows]),
    )
    return out.sort_index(), labels


def _merge_fx_daily_with_intraday(
    daily: pd.DataFrame,
    intraday_daily: pd.DataFrame,
) -> pd.DataFrame:
    daily_clean = _filter_fx_ohlc_frame(_normalize_daily_ohlc_frame(daily))
    if not daily_clean.empty:
        daily_clean = daily_clean.copy()
        daily_clean[FX_SOURCE_LABEL_COL] = FX_DAILY_SOURCE_LABEL
        daily_clean[FX_SOURCE_RANK_COL] = len(FX_INTRADAY_KLINE_SOURCES)
    if intraday_daily.empty:
        return daily_clean
    intraday_clean = _filter_fx_ohlc_frame(_normalize_daily_ohlc_frame(intraday_daily))
    if daily_clean.empty:
        return intraday_clean
    daily_clean = daily_clean[~daily_clean.index.isin(intraday_clean.index)]
    return pd.concat([daily_clean, intraday_clean]).sort_index()


def _fx_kline_source_notices(frame: pd.DataFrame) -> list[SeriesNotice]:
    if frame.empty or FX_SOURCE_LABEL_COL not in frame.columns:
        return []
    notices: list[SeriesNotice] = []
    labels = frame.sort_index()[FX_SOURCE_LABEL_COL].dropna()
    previous: str | None = None
    for ts, value in labels.items():
        label = str(value)
        if previous is not None and label != previous:
            day = pd.Timestamp(ts).date()
            notices.append(SeriesNotice(
                kind="fx_kline_source_change",
                date=day,
                text=f"口径切换：{day.isoformat()} 起 {label}，此前为 {previous}",
            ))
        previous = label
    return notices


def _build_fx_kline_series(
    src: DataSource,
    symbol: str,
    period_key: KlinePeriod,
    user_tz_name: str | None = None,
) -> AssetSeries:
    end = date.today()
    window_start = _fx_history_start(end)
    daily_frame = pd.DataFrame()
    daily_error: HTTPException | None = None
    try:
        daily_frame, _daily_symbol = _fetch_fx_daily_ohlc_with_fallback(
            src, symbol, window_start, end,
        )
    except HTTPException as exc:
        daily_error = exc
    intraday_daily = pd.DataFrame()
    intraday = _fetch_fx_intraday_ohlc_with_fallback(src, symbol)
    if intraday is not None:
        intraday_daily, _labels = _aggregate_fx_intraday_daily_ohlc(intraday[0])
    if daily_frame.empty and intraday_daily.empty:
        if daily_error is not None:
            raise daily_error
        raise HTTPException(404, f"No OHLC data for {symbol}")

    frame = _merge_fx_daily_with_intraday(daily_frame, intraday_daily)
    notices = _fx_kline_source_notices(frame)
    aggregated, labels = _aggregate_ohlc_frame(frame, period_key)
    if aggregated.empty:
        raise HTTPException(404, f"No OHLC data for {symbol}")

    ohlc = _ohlc_points_from_frame(aggregated, labels)
    points = [
        PricePoint(date=point.date, close=point.close, open=point.open)
        for point in ohlc
    ]
    display_tz = _user_tz(user_tz_name)
    return AssetSeries(
        symbol=symbol,
        range=f"{period_key}K",
        points=points,
        ohlc=ohlc,
        dividends=None,
        market=market_of(symbol),
        currency=currency_of(symbol),
        display_timezone=_tz_name(display_tz),
        quote=display_quote(src, symbol, now=_now_utc()),
        notices=notices or None,
    )


def _build_kline_series(
    src: DataSource,
    symbol: str,
    period_key: KlinePeriod,
    include_dividends: bool,
    start: date | None = None,
    filter_weekends: bool = False,
) -> AssetSeries:
    end = date.today()
    window_start = start or FULL_HISTORY_START
    try:
        frame = src.get_ohlc(symbol, window_start, end)
    except DataSourceError as e:
        raise HTTPException(404, str(e))
    if filter_weekends:
        frame = _filter_fx_ohlc_frame(frame)
    aggregated, labels = _aggregate_ohlc_frame(frame, period_key)
    if aggregated.empty:
        raise HTTPException(404, f"No OHLC data for {symbol}")

    ohlc = _ohlc_points_from_frame(aggregated, labels)
    points = [
        PricePoint(date=point.date, close=point.close, open=point.open)
        for point in ohlc
    ]

    dividends = None
    if include_dividends:
        d = src.get_dividends(symbol, window_start, end)
        if d is not None:
            dividends = [
                DividendPoint(date=ts.date(), amount=float(v))
                for ts, v in d.items()
            ]

    return AssetSeries(
        symbol=symbol,
        range=f"{period_key}K",
        points=points,
        ohlc=ohlc,
        dividends=dividends,
        quote=display_quote(src, symbol, now=_now_utc()),
    )


def _build_fx_series(
    src: DataSource,
    symbol: str,
    range_str: str,
    user_tz_name: str | None = None,
) -> AssetSeries:
    if range_str not in RANGE_DAYS and range_str not in {"today", "ytd"}:
        raise HTTPException(400, f"unknown range: {range_str}")
    display_tz = _user_tz(user_tz_name)
    if range_str == "today":
        intraday = _build_intraday_series(
            src, symbol, user_tz_name=user_tz_name,
            include_market_metadata=False,
        )
        return AssetSeries(
            symbol=symbol,
            range="today",
            points=[
                PricePoint(date=p.datetime, close=p.close)
                for p in intraday.points
            ],
            ohlc=None,
            dividends=None,
            currency=intraday.currency,
            display_timezone=intraday.display_timezone,
            quote=intraday.quote,
        )
    if range_str == "7d":
        return _build_multiday_intraday_asset_series(
            src, symbol, range_str, include_dividends=False,
            include_ohlc=True, display_tz=display_tz, include_quote=True,
            is_fx=True,
        )
    return _build_asset_series(
        src, symbol, range_str, include_dividends=False,
        include_ohlc=True, user_tz_name=user_tz_name,
    )


def _build_intraday_series(
    src: DataSource,
    symbol: str,
    period: str = "1d",
    interval: str = "5m",
    user_tz_name: str | None = None,
    include_market_metadata: bool = True,
    include_quote: bool = True,
) -> IntradaySeries:
    market = market_of(symbol)
    currency = currency_of(symbol)
    display_tz = tz_of(market) if include_market_metadata else _user_tz(user_tz_name)
    ref_day = None
    status = None
    if include_market_metadata:
        now = _now_utc()
        ref_day = ref_trading_day(market, now)
        status = market_status(market, now)
    try:
        prices = src.get_intraday_prices_tz(symbol, period=period, interval=interval)
    except DataSourceError as e:
        raise HTTPException(404, str(e))
    if include_market_metadata and ref_day is not None:
        prices, ref_day = _intraday_for_today(
            prices, market, ref_day, display_tz, interval, status,
        )
    if not include_market_metadata:
        prices = _series_to_display_tz(prices, display_tz)
    if include_quote:
        quote, prices = _intraday_quote(
            src, symbol, prices, ref_day, market, display_tz, status, interval,
            reject_quote_after_last=not include_market_metadata,
            prefer_quote_within_window=not include_market_metadata,
        )
    else:
        quote = None

    points = [
        IntradayPoint(datetime=ts.to_pydatetime(), close=float(v))
        for ts, v in prices.sort_index().items()
    ]
    return IntradaySeries(
        symbol=symbol,
        period=period,
        interval=interval,
        points=points,
        market_status=status,
        ref_day=ref_day,
        market=market,
        currency=currency,
        display_timezone=_tz_name(display_tz),
        quote=quote,
    )


@router.get("/asset/{symbol:path}/info", response_model=AssetInfo)
def get_asset_info(
    symbol: str,
    src: DataSource = Depends(get_data_source),
) -> AssetInfo:
    info = src.get_info(symbol)
    if info is None:
        return AssetInfo()
    return AssetInfo(**info)


@router.get("/asset-kline/{symbol:path}", response_model=AssetSeries)
def get_asset_kline(
    symbol: str,
    period: KlinePeriod = Query("day"),
    src: DataSource = Depends(get_data_source),
) -> AssetSeries:
    return _build_kline_series(src, symbol, period, include_dividends=True)


@router.get("/asset/{symbol:path}", response_model=AssetSeries)
def get_asset(
    symbol: str,
    range: Range = Query("1y"),
    ohlc: bool = Query(False),
    intraday: bool = Query(False),
    tz: str | None = Query(None),
    src: DataSource = Depends(get_data_source),
) -> AssetSeries:
    return _build_asset_series(
        src, symbol, range, include_dividends=True, include_ohlc=ohlc,
        intraday=intraday, user_tz_name=tz,
    )


@router.get("/index/{code:path}", response_model=AssetSeries)
def get_index(
    code: str,
    range: Range = Query("1y"),
    tz: str | None = Query(None),
    src: DataSource = Depends(get_data_source),
) -> AssetSeries:
    return _build_asset_series(src, code, range, include_dividends=False, user_tz_name=tz)


@router.get("/intraday/index/{code:path}", response_model=IntradaySeries)
def get_index_intraday(
    code: str,
    tz: str | None = Query(None),
    src: DataSource = Depends(get_data_source),
) -> IntradaySeries:
    return _build_intraday_series(src, code, user_tz_name=tz)


@router.get("/intraday/asset/{symbol:path}", response_model=IntradaySeries)
def get_asset_intraday(
    symbol: str,
    tz: str | None = Query(None),
    src: DataSource = Depends(get_data_source),
) -> IntradaySeries:
    return _build_intraday_series(src, symbol, user_tz_name=tz)


@router.get("/intraday/fx/{symbol:path}", response_model=IntradaySeries)
def get_fx_intraday(
    symbol: str,
    tz: str | None = Query(None),
    src: DataSource = Depends(get_data_source),
) -> IntradaySeries:
    return _build_intraday_series(
        src, symbol, user_tz_name=tz, include_market_metadata=False,
    )


@router.get("/fx/{symbol:path}", response_model=AssetSeries)
def get_fx(
    symbol: str,
    range: Range = Query("today"),
    tz: str | None = Query(None),
    src: DataSource = Depends(get_data_source),
) -> AssetSeries:
    return _build_fx_series(src, symbol, range, user_tz_name=tz)


@router.get("/fx-kline/{symbol:path}", response_model=AssetSeries)
def get_fx_kline(
    symbol: str,
    period: KlinePeriod = Query("day"),
    tz: str | None = Query(None),
    src: DataSource = Depends(get_data_source),
) -> AssetSeries:
    return _build_fx_kline_series(src, symbol, period, user_tz_name=tz)
