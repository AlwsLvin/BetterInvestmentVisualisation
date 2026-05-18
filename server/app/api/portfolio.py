from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from numbers import Real
from time import perf_counter
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from app.data.base import DataSource, DataSourceError
from app.data.market_hours import (
    close_time_of,
    market_status,
    previous_trading_day,
    ref_trading_day,
    tz_of,
)
from app.data.symbols import currency_of, market_of
from app.deps import get_data_source, get_settings
from app.schemas import (
    RANGE_DAYS,
    AssetMarketStatus,
    AllocateRequest,
    AllocateResponse,
    AssetMetricsOut,
    BacktestAllocationOut,
    BacktestDataWarning,
    BenchmarkPoint,
    BacktestPoint,
    BacktestPurchaseEvent,
    BacktestRequest,
    BacktestResponse,
    EvaluateRequest,
    EvaluateResponse,
    ExecutionWindowOut,
    HoldingMetricsOut,
    HoldingOut,
    RollingBacktestRequest,
    SettingsModel,
)
from app.services.allocation import allocate
from app.services.backtest import Plan, _as_ohlc_frame, _fx_rate, backtest, rolling_weight_backtest
from app.services.display_quote import display_quote
from app.services.evaluate import (
    RISK_FREE_PROXY_TICKER,
    _portfolio_close_series,
    evaluate_portfolio,
)
from app.services.metrics import annualized_return, compute_metrics_by_benchmark

router = APIRouter()
MIN_TRAINING_DAYS = 30
YEAR_ANCHORED_RANGES = {"1y": 1, "3y": 3, "5y": 5}
FETCH_WORKERS = 8

MARKET_BENCHMARKS = {
    "US": "^GSPC",
    "HK": "^HSI",
    "CN": "000300.SS",
    "JP": "^N225",
    "KR": "^KS11",
}


NASDAQ_EXCHANGE_CODES = {"NMS", "NGM", "NCM", "NAS"}


def _is_nasdaq_exchange(exchange: str | None) -> bool:
    if not exchange:
        return False
    normalized = exchange.strip().upper()
    return normalized in NASDAQ_EXCHANGE_CODES or "NASDAQ" in normalized


def _beta_benchmark_for(src: DataSource, symbol: str) -> str:
    market = market_of(symbol)
    if market == "US":
        try:
            if _is_nasdaq_exchange(src.get_exchange(symbol)):
                return "^IXIC"
        except Exception:
            pass
    return MARKET_BENCHMARKS.get(market, "^GSPC")


def _benchmark_label(symbols: list[str]) -> str:
    unique = sorted(set(symbols))
    if len(unique) == 1:
        return unique[0]
    return f"Composite ({', '.join(unique)})"


def _asset_metrics_out(metrics) -> AssetMetricsOut:
    return AssetMetricsOut(
        annualized_roi=metrics.annualized_roi,
        max_drawdown=metrics.max_drawdown,
        drawdown_duration=metrics.drawdown_duration,
        recovery_time=metrics.recovery_time,
        volatility=metrics.volatility,
        beta=metrics.beta,
        beta_benchmark=metrics.beta_benchmark,
        dividend_yield=metrics.dividend_yield,
    )


def _fetch_prices_and_dividends(
    src: DataSource,
    tickers: list[str],
    start: date,
    end: date,
):
    def load(t: str):
        try:
            return t, src.get_prices(t, start, end), src.get_dividends(t, start, end)
        except DataSourceError as e:
            raise HTTPException(404, f"{t}: {e}")

    prices = {}
    dividends = {}
    with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(tickers))) as pool:
        futures = [pool.submit(load, t) for t in tickers]
        for fut in as_completed(futures):
            ticker, price, dividend = fut.result()
            prices[ticker] = price
            dividends[ticker] = dividend
    return prices, dividends


def _fetch_ohlc(
    src: DataSource,
    tickers: list[str],
    start: date,
    end: date,
) -> dict[str, pd.DataFrame]:
    def load(t: str):
        try:
            return t, src.get_ohlc(t, start, end)
        except DataSourceError as e:
            raise HTTPException(404, f"{t}: {e}")
    out = {}
    with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(tickers))) as pool:
        futures = [pool.submit(load, t) for t in tickers]
        for fut in as_completed(futures):
            ticker, frame = fut.result()
            out[ticker] = frame
    return out


def _fetch_raw_ohlc(
    src: DataSource,
    tickers: list[str],
    start: date,
    end: date,
) -> dict[str, pd.DataFrame]:
    def load(t: str):
        try:
            return t, src.get_raw_ohlc(t, start, end)
        except DataSourceError as e:
            raise HTTPException(404, f"{t}: {e}")
    out = {}
    with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(tickers))) as pool:
        futures = [pool.submit(load, t) for t in tickers]
        for fut in as_completed(futures):
            ticker, frame = fut.result()
            out[ticker] = frame
    return out


def _fetch_cash_dividends(
    src: DataSource,
    tickers: list[str],
    start: date,
    end: date,
) -> dict[str, pd.Series | None]:
    with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(tickers))) as pool:
        futures = {pool.submit(src.get_cash_dividends, t, start, end): t for t in tickers}
        return {ticker: fut.result() for fut, ticker in futures.items()}


def _fetch_splits(
    src: DataSource,
    tickers: list[str],
    start: date,
    end: date,
) -> dict[str, pd.Series | None]:
    with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(tickers))) as pool:
        futures = {pool.submit(src.get_splits, t, start, end): t for t in tickers}
        return {ticker: fut.result() for fut, ticker in futures.items()}


def _fetch_intraday_prices(
    src: DataSource,
    tickers: list[str],
    period: str = "1d",
    interval: str = "5m",
) -> dict[str, pd.Series]:
    out = {}
    for t in tickers:
        try:
            out[t] = src.get_intraday_prices(t, period=period, interval=interval)
        except DataSourceError as e:
            raise HTTPException(404, f"{t}: {e}")
    return out


def _fx_symbol(currency: str) -> str:
    return f"USD{currency}=X"


def _currencies_for(tickers: list[str]) -> list[str]:
    return sorted({currency_of(t) for t in tickers if currency_of(t) != "USD"})


def _fetch_fx_rates(
    src: DataSource,
    currencies: list[str],
    start: date,
    end: date,
    intraday: bool = False,
    display_tz: ZoneInfo | None = None,
) -> dict[str, pd.Series | pd.DataFrame]:
    rates: dict[str, pd.Series | pd.DataFrame] = {}
    for ccy in currencies:
        symbol = _fx_symbol(ccy)
        try:
            if intraday:
                if display_tz is not None:
                    series = _series_to_display_tz(
                        src.get_intraday_prices_tz(symbol, period="5d"),
                        display_tz,
                    )
                    series.attrs["bar_minutes"] = 5
                    series.attrs["fx_source"] = "minute_asof"
                    rates[ccy] = series
                else:
                    series = src.get_intraday_prices(symbol, period="5d")
                    series.attrs["bar_minutes"] = 5
                    series.attrs["fx_source"] = "minute_asof"
                    rates[ccy] = series
            else:
                rates[ccy] = src.get_ohlc(symbol, start, end)
        except DataSourceError:
            if intraday:
                try:
                    rates[ccy] = src.get_ohlc(symbol, start - timedelta(days=7), end)
                    continue
                except DataSourceError as e:
                    raise HTTPException(502, f"{ccy} FX fetch failed: {e}")
            raise HTTPException(502, f"{ccy} FX fetch failed: {symbol}")
    return rates


def _fx_frame_with_meta(series: pd.Series, bar_minutes: int, source: str) -> pd.DataFrame:
    frame = pd.DataFrame({"Close": series.sort_index().dropna()})
    frame["_bar_minutes"] = bar_minutes
    frame["_fx_source"] = source
    frame["_priority"] = 0 if source == "minute_asof" else 1
    return frame


def _merge_fx_intraday_frames(frames: list[pd.DataFrame]) -> pd.DataFrame | None:
    clean = [frame for frame in frames if frame is not None and not frame.empty]
    if not clean:
        return None
    merged = pd.concat(clean).sort_index()
    merged = merged.sort_values(["_priority"], kind="stable")
    merged = merged[~merged.index.duplicated(keep="first")]
    merged = merged.sort_index()
    return merged.drop(columns=["_priority"])


def _fetch_fx_intraday_rates(
    src: DataSource,
    currencies: list[str],
    display_tz: ZoneInfo | None = None,
) -> dict[str, pd.Series | pd.DataFrame]:
    rates: dict[str, pd.DataFrame] = {}
    for ccy in currencies:
        symbol = _fx_symbol(ccy)
        frames: list[pd.DataFrame] = []
        try:
            series = src.get_intraday_prices_tz(symbol, period="7d", interval="1m")
            if display_tz:
                series = _series_to_display_tz(series, display_tz)
            frames.append(_fx_frame_with_meta(series, 1, "minute_asof"))
        except DataSourceError:
            pass
        try:
            series = src.get_intraday_prices_tz(symbol, period="60d", interval="5m")
            if display_tz:
                series = _series_to_display_tz(series, display_tz)
            frames.append(_fx_frame_with_meta(series, 5, "minute_asof"))
        except DataSourceError:
            pass
        try:
            series = src.get_intraday_prices_tz(symbol, period="730d", interval="60m")
            if display_tz:
                series = _series_to_display_tz(series, display_tz)
            frames.append(_fx_frame_with_meta(series, 60, "hourly_approx"))
        except DataSourceError:
            pass
        merged = _merge_fx_intraday_frames(frames)
        if merged is not None:
            rates[ccy] = merged
    return rates


def _fetch_market_benchmarks(
    src: DataSource,
    tickers: list[str],
    start: date,
    end: date,
) -> tuple[dict[str, str], dict[str, pd.Series]]:
    benchmark_by_ticker = {t: _beta_benchmark_for(src, t) for t in tickers}
    prices: dict[str, pd.Series] = {}
    symbols = sorted(set(benchmark_by_ticker.values()))

    def load(symbol: str):
        try:
            return symbol, src.get_prices(symbol, start, end)
        except DataSourceError as e:
            raise HTTPException(502, f"benchmark fetch failed for {symbol}: {e}")
    with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(symbols))) as pool:
        futures = [pool.submit(load, symbol) for symbol in symbols]
        for fut in as_completed(futures):
            symbol, series = fut.result()
            prices[symbol] = series
    return benchmark_by_ticker, prices


def _fetch_market_benchmarks_today(
    src: DataSource,
    tickers: list[str],
    now: datetime,
    user_tz: ZoneInfo,
) -> tuple[dict[str, str], dict[str, pd.Series]]:
    benchmark_by_ticker = {t: _beta_benchmark_for(src, t) for t in tickers}
    symbols = sorted(set(benchmark_by_ticker.values()))
    statuses = _today_asset_statuses(symbols, now)
    return benchmark_by_ticker, _today_intraday_prices(src, symbols, statuses, user_tz)


def _metrics_benchmarks_by_ticker(
    benchmark_by_ticker: dict[str, str],
    benchmark_prices: dict[str, pd.Series],
) -> dict[str, pd.Series]:
    return {t: benchmark_prices[benchmark_by_ticker[t]] for t in benchmark_by_ticker}


def _benchmark_components(
    benchmark_by_ticker: dict[str, str],
    weights: dict[str, float],
) -> dict[str, float]:
    components: dict[str, float] = {}
    for ticker, weight in weights.items():
        symbol = benchmark_by_ticker.get(ticker)
        if symbol is None:
            continue
        components[symbol] = components.get(symbol, 0.0) + float(weight)
    total = sum(components.values())
    if total <= 0:
        return {}
    return {symbol: value / total for symbol, value in components.items()}


def _normalize_weights(values: dict[str, float]) -> dict[str, float]:
    clean = {k: float(v) for k, v in values.items() if pd.notna(v) and float(v) > 0}
    total = sum(clean.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in clean.items()}


def _latest_usd_value_weights(
    prices: dict[str, pd.Series],
    weights: dict[str, float],
    fx_rates: dict[str, pd.Series | pd.DataFrame],
    ohlc: dict[str, pd.DataFrame] | None = None,
) -> dict[str, float]:
    try:
        close_sources: dict[str, pd.Series] = {}
        open_sources: dict[str, pd.Series] = {}
        for ticker in weights:
            frame = _as_ohlc_frame(ohlc[ticker]) if ohlc and ticker in ohlc else _as_ohlc_frame(prices[ticker])
            close_sources[ticker] = frame["Close"]
            open_sources[ticker] = frame["Open"]
        close_df = pd.concat(close_sources, axis=1).sort_index().ffill().dropna(how="any")
        if close_df.empty:
            return {}
        open_df = pd.concat(open_sources, axis=1).sort_index().reindex(close_df.index)
        base_day = close_df.index[0]
        last_day = close_df.index[-1]
        values: dict[str, float] = {}
        for ticker, weight in weights.items():
            currency = currency_of(ticker)
            base_open = float(open_df.at[base_day, ticker])
            if not pd.notna(base_open) or base_open <= 0:
                base_open = float(close_df.at[base_day, ticker])
            base_fx = _fx_rate(currency, base_day, fx_rates, "Open")
            last_fx = _fx_rate(currency, last_day, fx_rates, "Close")
            if base_fx is None or last_fx is None or base_open <= 0:
                continue
            latest_close = float(close_df.at[last_day, ticker])
            if not pd.notna(latest_close) or latest_close <= 0:
                continue
            base_usd = base_open / base_fx
            values[ticker] = float(weight) * (latest_close / last_fx) / base_usd
        return _normalize_weights(values)
    except Exception:
        return {}


def _composite_benchmark(
    benchmark_by_ticker: dict[str, str],
    benchmark_prices: dict[str, pd.Series],
    weights: dict[str, float],
    fx_rates: dict[str, pd.Series | pd.DataFrame],
) -> pd.Series | None:
    component_weights = _benchmark_components(benchmark_by_ticker, weights)
    if not component_weights:
        return None
    try:
        return _portfolio_close_series(
            benchmark_prices,
            component_weights,
            fx_rates=fx_rates,
        )
    except ValueError:
        return None


def _date_or_datetime(value):
    ts = pd.Timestamp(value)
    if ts.time() == pd.Timestamp(ts.date()).time():
        return ts.date()
    return ts.to_pydatetime()


def _benchmark_return_points(series: pd.Series | None) -> list[BenchmarkPoint]:
    if series is None or series.empty:
        return []
    clean = series.sort_index().dropna()
    if clean.empty:
        return []
    base = float(clean.iloc[0])
    if base <= 0:
        return []
    return [
        BenchmarkPoint(date=_date_or_datetime(d), return_pct=float(v / base - 1.0))
        for d, v in clean.items()
        if pd.notna(v)
    ]


def _usd_component_series(
    symbol: str,
    prices: pd.Series,
    fx_rates: dict[str, pd.Series | pd.DataFrame],
) -> pd.Series:
    clean = prices.sort_index().dropna()
    values = []
    index = []
    for when, price in clean.items():
        px = _finite_positive(price)
        if px is None:
            continue
        ts = pd.Timestamp(when)
        fx = _fx_rate(currency_of(symbol), ts, fx_rates, "Close")
        if fx is None:
            continue
        index.append(ts)
        values.append(px / fx)
    return pd.Series(values, index=pd.DatetimeIndex(index), name=symbol).sort_index()


def _today_benchmark_series(
    benchmark_prices: dict[str, pd.Series],
    component_weights: dict[str, float],
    fx_rates: dict[str, pd.Series | pd.DataFrame],
    timeline: list[pd.Timestamp],
) -> pd.Series | None:
    if not component_weights or not timeline:
        return None
    timeline_index = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in timeline}))
    if timeline_index.empty:
        return None

    parts: dict[str, pd.Series] = {}
    included_weights: dict[str, float] = {}
    for symbol, weight in component_weights.items():
        series = benchmark_prices.get(symbol)
        if series is None:
            continue
        usd = _usd_component_series(symbol, series, fx_rates)
        if usd.empty:
            continue
        first_actual = usd.index[0]
        carried = usd.reindex(timeline_index.union(usd.index).sort_values()).ffill()
        carried = carried.reindex(timeline_index)
        base = (
            float(carried.iloc[0])
            if pd.notna(carried.iloc[0]) and float(carried.iloc[0]) > 0
            else float(usd.iloc[0])
        )
        if base <= 0:
            continue
        norm = (carried / base).copy()
        norm.loc[timeline_index < first_actual] = 1.0
        norm = norm.ffill().fillna(1.0)
        parts[symbol] = norm
        included_weights[symbol] = float(weight)

    total = sum(included_weights.values())
    if not parts or total <= 0:
        return None
    out = pd.Series(0.0, index=timeline_index, name="benchmark")
    for symbol, series in parts.items():
        out = out.add(series * (included_weights[symbol] / total), fill_value=0.0)
    return out.sort_index()


def _finite_positive(value) -> float | None:
    if isinstance(value, Real) and isfinite(float(value)) and float(value) > 0:
        return float(value)
    return None


def _finite_number(value) -> float | None:
    if isinstance(value, Real) and isfinite(float(value)):
        return float(value)
    return None


def _series_step_return(series: pd.Series) -> float | None:
    clean = series.sort_index().dropna()
    if len(clean) < 2:
        return None
    latest = _finite_positive(clean.iloc[-1])
    previous = _finite_positive(clean.iloc[-2])
    if latest is None or previous is None:
        return None
    return latest / previous - 1.0


def _recent_raw_daily_change(
    src: DataSource,
    symbol: str,
    end: date,
) -> float | None:
    try:
        df = src.get_raw_ohlc(symbol, end - timedelta(days=14), end)
    except DataSourceError:
        return None
    if df.empty or "Close" not in df.columns:
        return None
    return _series_step_return(df["Close"])


def _display_daily_change(
    src: DataSource,
    symbol: str,
    end: date,
    fallback_series: pd.Series,
) -> float | None:
    quote = display_quote(src, symbol, now=_now_utc())
    quote_change = _finite_number(quote.get("change_pct")) if quote else None
    if quote_change is not None:
        return quote_change
    return _series_step_return(fallback_series)


def _display_time(value, display_tz: ZoneInfo) -> pd.Timestamp | None:
    if not isinstance(value, datetime):
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    return ts.tz_convert(display_tz).tz_localize(None)


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


def _today_display_price_and_change(
    src: DataSource,
    symbol: str,
    series: pd.Series,
    status: AssetMarketStatus | None,
    display_tz: ZoneInfo,
    interval: str = "5m",
) -> tuple[float | None, float | None]:
    raw = src.get_quote(symbol) or {}
    quote_last = _finite_positive(raw.get("last_price"))
    sorted_series = series.sort_index().dropna()
    intraday_last = _finite_positive(sorted_series.iloc[-1]) if not sorted_series.empty else None

    as_of = raw.get("as_of")
    quote_target = _display_time(as_of, display_tz)
    if (
        quote_last is not None
        and quote_target is not None
        and not sorted_series.empty
        and quote_target < sorted_series.index[-1] - _interval_delta(interval) * 2
    ):
        quote_last = None

    ref_day = status.ref_day if status is not None else None
    daily_close = None
    if ref_day is not None and status is not None and status.status == "closed":
        daily_close = _daily_close_on(src, symbol, ref_day, fresh=True)
    if status is not None and status.status == "closed":
        latest = daily_close or quote_last or intraday_last
    else:
        latest = quote_last or intraday_last

    previous_close = _finite_positive(raw.get("previous_close"))
    if ref_day is not None:
        previous_close = _previous_close_before(src, symbol, ref_day) or previous_close

    daily_change = (
        latest / previous_close - 1.0
        if latest is not None and previous_close is not None else None
    )
    return latest, daily_change


def _execution_windows_for_today(
    ohlc: dict[str, pd.DataFrame],
    statuses: dict[str, AssetMarketStatus],
    display_timezone: str,
    training_start: date,
    training_end: date,
) -> dict[str, ExecutionWindowOut]:
    out: dict[str, ExecutionWindowOut] = {}
    for ticker, status in statuses.items():
        frame = ohlc.get(ticker)
        start_dt = None
        end_dt = None
        if frame is not None and not frame.empty:
            index = frame.sort_index().index
            start_dt = pd.Timestamp(index[0]).to_pydatetime()
            end_dt = pd.Timestamp(index[-1]).to_pydatetime()
        out[ticker] = ExecutionWindowOut(
            ticker=ticker,
            market=status.market,
            currency=status.currency,
            market_timezone=status.timezone,
            display_timezone=display_timezone,
            ref_day=status.ref_day,
            market_status=status.status,
            execution_start=start_dt,
            execution_end=end_dt,
            training_start=training_start,
            training_end=training_end,
        )
    return out


def _slice_series(series, start: date, end: date):
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    return series.loc[
        (series.index >= start_ts) & (series.index <= end_ts)
    ]


def _series_date(value) -> date:
    ts = pd.Timestamp(value)
    return ts.date()


def _training_warning(
    ticker: str,
    year: int,
    train_start: date,
    train_end: date,
    series: pd.Series,
    benchmark_count: int,
    min_training_days: int = MIN_TRAINING_DAYS,
) -> BacktestDataWarning | None:
    clean = series.dropna()
    sample_count = len(clean)
    available_start = _series_date(clean.index[0]) if sample_count else None
    available_end = _series_date(clean.index[-1]) if sample_count else None
    if sample_count < min_training_days:
        return BacktestDataWarning(
            ticker=ticker,
            year=year,
            training_start=train_start,
            training_end=train_end,
            available_start=available_start,
            available_end=available_end,
            sample_count=sample_count,
            action="excluded",
            message=(
                f"{ticker} has only {sample_count} training samples for {year}; "
                "excluded from this year's allocation."
            ),
        )
    if benchmark_count > 0 and sample_count < benchmark_count * 0.9:
        return BacktestDataWarning(
            ticker=ticker,
            year=year,
            training_start=train_start,
            training_end=train_end,
            available_start=available_start,
            available_end=available_end,
            sample_count=sample_count,
            action="annualized_short_history",
            message=(
                f"{ticker} has partial training history for {year}; metrics were "
                "annualized from the available window."
            ),
        )
    return None


def _min_training_days_for_lookback(lookback_days: int) -> int:
    return min(MIN_TRAINING_DAYS, max(5, int(round(lookback_days * 0.6))))


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


def _today_asset_statuses(
    tickers: list[str],
    at: datetime | None = None,
) -> dict[str, AssetMarketStatus]:
    now = at or _now_utc()
    out: dict[str, AssetMarketStatus] = {}
    for symbol in tickers:
        market = market_of(symbol)
        out[symbol] = AssetMarketStatus(
            market=market,
            ref_day=ref_trading_day(market, now),
            status=market_status(market, now),
            currency=currency_of(symbol),
            timezone=_tz_name(tz_of(market)),
        )
    return out


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
    if pd.Timedelta(0) < delta <= _interval_delta(interval):
        target = close_local.tz_convert(user_tz).tz_localize(None)
        if target not in series.index:
            out = series.copy()
            new_index = list(out.index)
            new_index[-1] = target
            out.index = pd.DatetimeIndex(new_index)
            return out.sort_index()
    return series


def _intraday_for_status(
    series: pd.Series,
    status: AssetMarketStatus,
    user_tz: ZoneInfo,
    interval: str = "5m",
) -> tuple[pd.Series, date]:
    if series.empty or not isinstance(series.index, pd.DatetimeIndex):
        return series.sort_index(), status.ref_day
    sorted_series = series.sort_index()
    local_index = _market_local_index(sorted_series.index, status.market)
    available_days = sorted({ts.date() for ts in local_index if ts.date() <= status.ref_day})
    if not available_days:
        available_days = sorted({ts.date() for ts in local_index})
        if not available_days:
            return sorted_series.iloc[0:0], status.ref_day
    selected_day = status.ref_day if status.ref_day in available_days else available_days[-1]
    mask = [ts.date() == selected_day for ts in local_index]
    selected = sorted_series.loc[mask]
    selected_index = local_index[mask]
    out = selected.copy()
    out.index = selected_index.tz_convert(user_tz).tz_localize(None)
    out = _label_closed_market_final_bar(
        out, selected_index, status.market, selected_day,
        user_tz, interval, status.status,
    )
    return out.sort_index(), selected_day


def _series_to_display_tz(series: pd.Series, display_tz: ZoneInfo) -> pd.Series:
    if series.empty or not isinstance(series.index, pd.DatetimeIndex):
        return series.sort_index()
    out = series.sort_index().copy()
    if out.index.tz is None:
        out.index = out.index.tz_localize(ZoneInfo("UTC"))
    out.index = out.index.tz_convert(display_tz).tz_localize(None)
    return out.sort_index()


def _today_intraday_prices(
    src: DataSource,
    tickers: list[str],
    statuses: dict[str, AssetMarketStatus],
    user_tz: ZoneInfo,
) -> dict[str, pd.Series]:
    raw: dict[str, pd.Series] = {}
    for symbol in tickers:
        try:
            raw[symbol] = src.get_intraday_prices_tz(symbol, period="5d")
        except DataSourceError as e:
            raise HTTPException(404, f"{symbol}: {e}")
    out: dict[str, pd.Series] = {}
    for symbol, series in raw.items():
        selected, selected_day = _intraday_for_status(series, statuses[symbol], user_tz)
        statuses[symbol].ref_day = selected_day
        out[symbol] = selected
    return out


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
    if pd.Timedelta(0) < delta <= _interval_delta(interval):
        target = close_local.tz_convert(user_tz).tz_localize(None)
        if target not in frame.index:
            out = frame.copy()
            new_index = list(out.index)
            new_index[-1] = target
            out.index = pd.DatetimeIndex(new_index)
            return out.sort_index()
    return frame


def _intraday_ohlc_for_status(
    frame: pd.DataFrame,
    status: AssetMarketStatus,
    user_tz: ZoneInfo,
    interval: str = "5m",
) -> tuple[pd.DataFrame, date]:
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return frame.sort_index(), status.ref_day
    sorted_frame = frame.sort_index()
    local_index = _market_local_index(sorted_frame.index, status.market)
    available_days = sorted({ts.date() for ts in local_index if ts.date() <= status.ref_day})
    if not available_days:
        available_days = sorted({ts.date() for ts in local_index})
        if not available_days:
            return sorted_frame.iloc[0:0], status.ref_day
    selected_day = status.ref_day if status.ref_day in available_days else available_days[-1]
    mask = [ts.date() == selected_day for ts in local_index]
    selected = sorted_frame.loc[mask].copy()
    selected_index = local_index[mask]
    selected.index = selected_index.tz_convert(user_tz).tz_localize(None)
    selected = _label_closed_market_final_frame(
        selected, selected_index, status.market, selected_day,
        user_tz, interval, status.status,
    )
    return selected.sort_index(), selected_day


def _today_intraday_ohlc(
    src: DataSource,
    tickers: list[str],
    statuses: dict[str, AssetMarketStatus],
    user_tz: ZoneInfo,
) -> dict[str, pd.DataFrame]:
    raw: dict[str, pd.DataFrame] = {}
    for symbol in tickers:
        try:
            raw[symbol] = src.get_intraday_ohlc_tz(symbol, period="5d")
        except DataSourceError as e:
            raise HTTPException(404, f"{symbol}: {e}")
    out: dict[str, pd.DataFrame] = {}
    for symbol, frame in raw.items():
        selected, selected_day = _intraday_ohlc_for_status(frame, statuses[symbol], user_tz)
        statuses[symbol].ref_day = selected_day
        out[symbol] = selected
    return out


def _rolling_execution_start(end: date, range_key: str) -> date:
    if range_key == "today":
        return end
    if range_key in YEAR_ANCHORED_RANGES:
        return _shift_years(end + timedelta(days=1), -YEAR_ANCHORED_RANGES[range_key])
    if range_key == "ytd":
        return date(end.year, 1, 1)
    return end - timedelta(days=RANGE_DAYS[range_key])


def _range_end(end: date, range_key: str) -> date:
    if range_key in YEAR_ANCHORED_RANGES:
        return previous_trading_day("US", end)
    return end


def _range_start(end: date, range_key: str) -> date:
    if range_key == "today":
        return end
    if range_key == "ytd":
        return date(end.year, 1, 1)
    if range_key in YEAR_ANCHORED_RANGES:
        return _shift_years(end + timedelta(days=1), -YEAR_ANCHORED_RANGES[range_key])
    return end - timedelta(days=RANGE_DAYS[range_key])


def _shift_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _rolling_training_years(range_key: str) -> int:
    return YEAR_ANCHORED_RANGES.get(range_key, 1)


def _rolling_execution_segments(
    start: date,
    end: date,
    range_key: str,
    lookback_days: int = 365,
) -> list[tuple[date, date]]:
    if start > end:
        return []
    if lookback_days != 365:
        segments_reversed: list[tuple[date, date]] = []
        segment_end = end
        segment_days = max(1, int(lookback_days))
        while segment_end >= start:
            segment_start = max(start, segment_end - timedelta(days=segment_days - 1))
            segments_reversed.append((segment_start, segment_end))
            segment_end = segment_start - timedelta(days=1)
        return list(reversed(segments_reversed))

    if range_key in YEAR_ANCHORED_RANGES:
        segments: list[tuple[date, date]] = []
        cur = start
        while cur <= end:
            next_start = _shift_years(cur, 1)
            seg_end = min(next_start - timedelta(days=1), end)
            segments.append((cur, seg_end))
            cur = next_start
        return segments

    segments = []
    for year in range(start.year, end.year + 1):
        seg_start = max(start, date(year, 1, 1))
        seg_end = min(end, date(year, 12, 31))
        if seg_start <= seg_end:
            segments.append((seg_start, seg_end))
    return segments


def _training_window_for_segment(
    effective_start: date,
    range_key: str,
    lookback_days: int = 365,
) -> tuple[date, date]:
    return effective_start - timedelta(days=lookback_days), effective_start - timedelta(days=1)


def _rf_window(start: date) -> tuple[date, date]:
    return start - timedelta(days=365), start


def _fetch_bil_rf_default(
    src: DataSource,
    start: date,
) -> tuple[float | None, date, date]:
    rf_start, rf_end = _rf_window(start)
    try:
        bil = src.get_prices(RISK_FREE_PROXY_TICKER, rf_start, rf_end)
    except DataSourceError:
        return None, rf_start, rf_end
    clean = bil.dropna()
    if len(clean) < 2:
        return None, rf_start, rf_end
    return float(annualized_return(clean)), rf_start, rf_end


def _backtest_response(
    bt,
    schedule: list[BacktestAllocationOut] | None = None,
    range_key: str | None = None,
    per_asset_status: dict[str, AssetMarketStatus] | None = None,
    display_timezone: str | None = None,
    data_warnings: list[BacktestDataWarning] | None = None,
    benchmark: str | None = None,
    benchmark_components: dict[str, float] | None = None,
    benchmark_points: list[BenchmarkPoint] | None = None,
    execution_windows: dict[str, ExecutionWindowOut] | None = None,
    timings: dict[str, float] | None = None,
) -> BacktestResponse:
    annualized = bt.annualized_return
    if range_key == "today":
        annualized = None
    points = [
        BacktestPoint(
            date=d.to_pydatetime() if getattr(d, "time", lambda: None)() != pd.Timestamp(d.date()).time() else d.date(),
            nav=nav,
            cash_invested=cash,
            return_pct=ret,
        )
        for d, nav, cash, ret in zip(bt.dates, bt.nav, bt.cash_invested, bt.return_pct)
    ]
    return BacktestResponse(
        points=points,
        invest_dates=[d.date() for d in bt.invest_dates],
        cumulative_return=bt.cumulative_return,
        annualized_return=annualized,
        max_drawdown=bt.max_drawdown,
        final_nav=bt.final_nav,
        total_invested=bt.total_invested,
        per_asset_final_value=bt.per_asset_final_value,
        cash_left=bt.cash_left,
        allocation_schedule=schedule or [],
        per_asset_status=per_asset_status or {},
        display_timezone=display_timezone,
        data_warnings=data_warnings or [],
        benchmark=benchmark,
        benchmark_components=benchmark_components or {},
        benchmark_points=benchmark_points or [],
        execution_windows=execution_windows or {},
        timings=timings or {},
        purchase_events=[
            BacktestPurchaseEvent(
                ticker=e.ticker,
                market=e.market,
                timezone=e.timezone,
                purchased_at_timezone=e.purchased_at_timezone,
                purchased_at=e.purchased_at,
                currency=e.currency,
                price=e.price,
                fx_rate=e.fx_rate,
                fx_source=e.fx_source,
                fx_as_of=e.fx_as_of,
                fx_alignment_note=e.fx_alignment_note,
                price_usd=e.price_usd,
                shares=e.shares,
                total_shares=e.total_shares,
            )
            for e in getattr(bt, "purchase_events", [])
        ],
    )


@router.post("/portfolio/allocate", response_model=AllocateResponse)
def allocate_portfolio(
    req: AllocateRequest,
    src: DataSource = Depends(get_data_source),
    settings: SettingsModel = Depends(get_settings),
) -> AllocateResponse:
    end = date.today()
    start = end - timedelta(days=req.lookback_days)
    prices, dividends = _fetch_prices_and_dividends(src, req.tickers, start, end)
    benchmark_by_ticker, benchmark_prices = _fetch_market_benchmarks(
        src, req.tickers, start, end,
    )

    metrics = compute_metrics_by_benchmark(
        prices,
        _metrics_benchmarks_by_ticker(benchmark_by_ticker, benchmark_prices),
        dividends,
        benchmark_by_ticker,
    )
    result = allocate(
        metrics,
        style=req.style,
        scheme=req.scheme,
        tau=req.tau,
        power=req.power,
        floor=req.floor,
        spread_pct=req.spread_pct,
    )

    metrics_out = {t: _asset_metrics_out(m) for t, m in metrics.items()}

    return AllocateResponse(
        tickers=result.tickers,
        indicators=result.indicators,
        style=result.style,
        scheme=result.scheme,
        has_dividend=result.has_dividend,
        global_weights=result.global_weights,
        metrics=metrics_out,
        closeness=result.closeness,
        allocation=result.allocation,
        constant_criteria=result.constant_criteria,
    )


@router.post("/backtest/rolling-allocation", response_model=BacktestResponse)
def rolling_allocation_backtest(
    req: RollingBacktestRequest,
    src: DataSource = Depends(get_data_source),
    settings: SettingsModel = Depends(get_settings),
) -> BacktestResponse:
    timings: dict[str, float] = {}
    request_started = perf_counter()
    end = _range_end(date.today(), req.range)
    start = _rolling_execution_start(end, req.range)
    allocation_lookback_days = int(settings.allocation_lookback_days)
    segments = _rolling_execution_segments(start, end, req.range, allocation_lookback_days)
    if not segments:
        raise HTTPException(400, "empty rolling execution window")
    training_windows = [
        _training_window_for_segment(segment_start, req.range, allocation_lookback_days)
        for segment_start, _segment_end in segments
    ]
    min_training_days = _min_training_days_for_lookback(allocation_lookback_days)
    fetch_start = min(train_start for train_start, _train_end in training_windows)

    t0 = perf_counter()
    prices, dividends = _fetch_prices_and_dividends(src, req.tickers, fetch_start, end)
    benchmark_by_ticker, benchmark_prices = _fetch_market_benchmarks(
        src, req.tickers, fetch_start, end,
    )
    timings["training_data_fetch_ms"] = round((perf_counter() - t0) * 1000, 2)

    scheduled_weights: list[tuple[date, date, dict[str, float]]] = []
    schedule: list[BacktestAllocationOut] = []
    data_warnings: list[BacktestDataWarning] = []

    t0 = perf_counter()
    for (effective_start, effective_end), (train_start, train_end) in zip(segments, training_windows):
        execution_year = effective_end.year
        train_prices_all = {
            t: _slice_series(prices[t], train_start, train_end).dropna()
            for t in req.tickers
        }
        train_benchmarks = {
            t: _slice_series(
                benchmark_prices[benchmark_by_ticker[t]], train_start, train_end,
            ).dropna()
            for t in req.tickers
        }
        if any(s.empty for s in train_benchmarks.values()):
            raise HTTPException(
                400,
                f"insufficient benchmark data for execution year {execution_year}",
            )
        train_prices = {}
        for t, series in train_prices_all.items():
            warning = _training_warning(
                t, execution_year, train_start, train_end, series,
                len(train_benchmarks[t]), min_training_days,
            )
            if warning is not None:
                data_warnings.append(warning)
            if warning is not None and warning.action == "excluded":
                continue
            train_prices[t] = series
        if not train_prices:
            raise HTTPException(
                400,
                f"all tickers have fewer than {min_training_days} training samples "
                f"for execution year {execution_year}",
            )
        train_dividends = {
            t: _slice_series(dividends[t], train_start, train_end)
            if dividends[t] is not None else None
            for t in train_prices
        }
        metrics = compute_metrics_by_benchmark(
            train_prices,
            {t: train_benchmarks[t] for t in train_prices},
            train_dividends,
            {t: benchmark_by_ticker[t] for t in train_prices},
        )
        result = allocate(
            metrics,
            style=req.style,
            scheme=req.scheme,
            tau=req.tau,
            power=req.power,
            floor=req.floor,
            spread_pct=req.spread_pct,
        )
        scheduled_weights.append((effective_start, effective_end, result.allocation))
        schedule.append(BacktestAllocationOut(
            year=execution_year,
            effective_start=effective_start,
            effective_end=effective_end,
            training_start=train_start,
            training_end=train_end,
            allocation=result.allocation,
            metrics={t: _asset_metrics_out(m) for t, m in metrics.items()},
            global_weights=result.global_weights,
            closeness=result.closeness,
            indicators=result.indicators,
            has_dividend=result.has_dividend,
            constant_criteria=result.constant_criteria,
        ))
    timings["allocation_ms"] = round((perf_counter() - t0) * 1000, 2)

    per_asset_status: dict[str, AssetMarketStatus] = {}
    display_timezone = None
    execution_windows: dict[str, ExecutionWindowOut] = {}
    exec_benchmark_prices = {
        symbol: _slice_series(series, start, end)
        for symbol, series in benchmark_prices.items()
    }
    try:
        t0 = perf_counter()
        if req.range == "today":
            user_tz = _user_tz(req.tz)
            display_timezone = _tz_name(user_tz)
            now = _now_utc()
            per_asset_status = _today_asset_statuses(req.tickers, now)
            exec_ohlc = _today_intraday_ohlc(src, req.tickers, per_asset_status, user_tz)
            exec_benchmark_by_ticker, exec_benchmark_prices = _fetch_market_benchmarks_today(
                src, req.tickers, now, user_tz,
            )
            exec_prices = {
                t: _as_ohlc_frame(frame)["Close"]
                for t, frame in exec_ohlc.items()
            }
            exec_dividends = None
            exec_splits = None
            exec_fx = _fetch_fx_rates(
                src, _currencies_for(req.tickers), start, end, intraday=True,
                display_tz=user_tz,
            )
            exec_fx_intraday = exec_fx
            execution_windows = _execution_windows_for_today(
                exec_ohlc,
                per_asset_status,
                display_timezone,
                training_windows[-1][0],
                training_windows[-1][1],
            )
            timings["execution_data_fetch_ms"] = round((perf_counter() - t0) * 1000, 2)
            t0 = perf_counter()
            bt = backtest(
                exec_prices,
                scheduled_weights[-1][2],
                Plan(amount=req.plan.amount, frequency=req.plan.frequency),
                start,
                end,
                ohlc=exec_ohlc,
                fx_rates=exec_fx,
                fx_intraday_rates=exec_fx_intraday,
                dividends=exec_dividends,
                splits=exec_splits,
                timeline_tz=user_tz,
            )
        else:
            exec_benchmark_by_ticker = benchmark_by_ticker
            exec_prices = prices
            exec_ohlc = _fetch_raw_ohlc(src, req.tickers, start, end)
            exec_dividends = _fetch_cash_dividends(src, req.tickers, start, end)
            exec_splits = _fetch_splits(src, req.tickers, start, end)
            exec_fx = _fetch_fx_rates(src, _currencies_for(req.tickers), start, end)
            exec_fx_intraday = _fetch_fx_intraday_rates(src, _currencies_for(req.tickers))
            timings["execution_data_fetch_ms"] = round((perf_counter() - t0) * 1000, 2)
            t0 = perf_counter()
            bt = rolling_weight_backtest(
                exec_prices,
                scheduled_weights,
                Plan(amount=req.plan.amount, frequency=req.plan.frequency),
                start,
                end,
                ohlc=exec_ohlc,
                fx_rates=exec_fx,
                fx_intraday_rates=exec_fx_intraday,
                dividends=exec_dividends,
                splits=exec_splits,
                timeline_tz=None,
            )
        timings["simulation_ms"] = round((perf_counter() - t0) * 1000, 2)
    except ValueError as e:
        raise HTTPException(400, str(e))

    t0 = perf_counter()
    benchmark_weight_source = _normalize_weights(bt.per_asset_final_value)
    if not benchmark_weight_source and scheduled_weights:
        benchmark_weight_source = scheduled_weights[-1][2]
    benchmark_components = _benchmark_components(exec_benchmark_by_ticker, benchmark_weight_source)
    benchmark_series = None
    if benchmark_components:
        try:
            if req.range == "today":
                benchmark_series = _today_benchmark_series(
                    exec_benchmark_prices,
                    benchmark_components,
                    exec_fx,
                    bt.dates,
                )
            else:
                benchmark_series = _portfolio_close_series(
                    exec_benchmark_prices,
                    benchmark_components,
                    fx_rates=exec_fx,
                )
        except ValueError:
            benchmark_series = None
    benchmark_points = _benchmark_return_points(benchmark_series)
    timings["benchmark_ms"] = round((perf_counter() - t0) * 1000, 2)
    timings["total_ms"] = round((perf_counter() - request_started) * 1000, 2)

    return _backtest_response(
        bt, schedule, req.range, per_asset_status=per_asset_status,
        display_timezone=display_timezone, data_warnings=data_warnings,
        benchmark=_benchmark_label(list(benchmark_components)) if benchmark_components else None,
        benchmark_components=benchmark_components,
        benchmark_points=benchmark_points,
        execution_windows=execution_windows,
        timings=timings,
    )


@router.post("/portfolio/evaluate", response_model=EvaluateResponse)
def evaluate(
    req: EvaluateRequest,
    src: DataSource = Depends(get_data_source),
    settings: SettingsModel = Depends(get_settings),
) -> EvaluateResponse:
    if abs(sum(req.weights.values()) - 1.0) > 1e-3:
        raise HTTPException(400, "weights must sum to 1")

    end = _range_end(date.today(), req.range)
    start = _range_start(end, req.range)

    tickers = list(req.weights.keys())
    rf_default, rf_window_start, rf_window_end = (
        (None, None, None)
        if req.rf_override is not None
        else _fetch_bil_rf_default(src, start)
    )

    per_asset_status: dict[str, AssetMarketStatus] = {}
    today_display_tz: ZoneInfo | None = None
    if req.range == "today":
        user_tz = _user_tz(req.tz)
        today_display_tz = user_tz
        now = _now_utc()
        all_status = _today_asset_statuses(tickers, now)
        per_asset_status = {t: all_status[t] for t in tickers}
        ohlc = _today_intraday_ohlc(src, tickers, all_status, user_tz)
        prices = {
            t: _as_ohlc_frame(frame)["Close"]
            for t, frame in ohlc.items()
        }
        dividends = {t: None for t in tickers}
        fx_rates = _fetch_fx_rates(
            src, _currencies_for(tickers), start, end, intraday=True,
            display_tz=user_tz,
        )
        benchmark_by_ticker, benchmark_prices = _fetch_market_benchmarks_today(
            src, tickers, now, user_tz,
        )
    else:
        prices, dividends = _fetch_prices_and_dividends(src, tickers, start, end)
        ohlc = _fetch_ohlc(src, tickers, start, end)
        fx_rates = _fetch_fx_rates(src, _currencies_for(tickers), start, end)
        benchmark_by_ticker, benchmark_prices = _fetch_market_benchmarks(
            src, tickers, start, end,
        )

    metrics = compute_metrics_by_benchmark(
        {t: prices[t] for t in tickers},
        _metrics_benchmarks_by_ticker(benchmark_by_ticker, benchmark_prices),
        {t: dividends[t] for t in tickers},
        benchmark_by_ticker,
    )
    benchmark_weight_source = _latest_usd_value_weights(prices, req.weights, fx_rates, ohlc)
    if not benchmark_weight_source:
        benchmark_weight_source = req.weights
    benchmark_components = _benchmark_components(benchmark_by_ticker, benchmark_weight_source)
    composite_benchmark = None
    if not (req.range == "today" and len({market_of(t) for t in tickers}) > 1):
        try:
            composite_benchmark = _portfolio_close_series(
                benchmark_prices,
                benchmark_components,
                fx_rates=fx_rates,
            )
        except ValueError:
            composite_benchmark = None

    try:
        evaluation = evaluate_portfolio(
            prices,
            req.weights,
            composite_benchmark,
            rf_override=req.rf_override,
            rf_default=rf_default,
            ohlc=ohlc,
            fx_rates=fx_rates,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    holdings: list[HoldingOut] = []
    for t, w in req.weights.items():
        series = prices[t]
        last_price = float(series.iloc[-1]) if len(series) else None
        daily_change = _display_daily_change(src, t, end, series)
        if req.range == "today" and today_display_tz is not None:
            last_price, daily_change = _today_display_price_and_change(
                src, t, series, per_asset_status.get(t), today_display_tz,
            )
        currency = currency_of(t)
        last_fx = _fx_rate(currency, series.index[-1], fx_rates, "Close") if len(series) else None
        last_price_usd = (
            last_price / last_fx
            if last_price is not None and last_fx is not None else None
        )
        period_return = None
        if len(series) >= 2:
            frame = _as_ohlc_frame(ohlc[t]) if ohlc and t in ohlc else _as_ohlc_frame(series)
            first_day = frame.index[0]
            base_open = float(frame["Open"].iloc[0])
            base_fx = _fx_rate(currency, first_day, fx_rates, "Open")
            if base_open > 0 and base_fx is not None and last_price_usd is not None:
                period_return = float(last_price_usd / (base_open / base_fx) - 1.0)
        m = metrics.get(t)
        holdings.append(HoldingOut(
            ticker=t, weight=w, currency=currency,
            last_price=last_price,
            last_price_usd=last_price_usd,
            daily_change=daily_change,
            period_return=period_return,
            metrics=HoldingMetricsOut(
                annualized_roi=m.annualized_roi,
                max_drawdown=m.max_drawdown,
                volatility=m.volatility,
                beta=m.beta,
                beta_benchmark=m.beta_benchmark,
                dividend_yield=m.dividend_yield,
            ) if m else None,
        ))

    return EvaluateResponse(
        range=req.range,
        portfolio={
            "cumulative_return": evaluation.cumulative_return,
            "annualized_return": evaluation.annualized_return,
            "volatility": evaluation.volatility,
            "max_drawdown": evaluation.max_drawdown,
            "beta": evaluation.beta,
            "alpha": evaluation.alpha,
            "sharpe": evaluation.sharpe,
        },
        holdings=holdings,
        benchmark=_benchmark_label(list(benchmark_by_ticker.values())),
        benchmark_components=benchmark_components,
        rf_used=evaluation.rf_used,
        rf_source=evaluation.rf_source,
        rf_window_start=rf_window_start,
        rf_window_end=rf_window_end,
        per_asset_status=per_asset_status,
    )


@router.post("/backtest", response_model=BacktestResponse)
def backtest_portfolio(
    req: BacktestRequest,
    src: DataSource = Depends(get_data_source),
) -> BacktestResponse:
    if abs(sum(req.weights.values()) - 1.0) > 1e-3:
        raise HTTPException(400, "weights must sum to 1")
    end = _range_end(date.today(), req.range)
    start = _range_start(end, req.range)
    tickers = list(req.weights.keys())
    per_asset_status: dict[str, AssetMarketStatus] = {}
    display_timezone = None
    if req.range == "today":
        user_tz = _user_tz(req.tz)
        display_timezone = _tz_name(user_tz)
        now = _now_utc()
        per_asset_status = _today_asset_statuses(tickers, now)
        ohlc = _today_intraday_ohlc(src, tickers, per_asset_status, user_tz)
        prices = {
            t: _as_ohlc_frame(frame)["Close"]
            for t, frame in ohlc.items()
        }
        dividends = None
        splits = None
        fx_rates = _fetch_fx_rates(
            src, _currencies_for(tickers), start, end, intraday=True,
            display_tz=user_tz,
        )
        fx_intraday_rates = fx_rates
    else:
        prices, _ = _fetch_prices_and_dividends(src, tickers, start, end)
        ohlc = _fetch_raw_ohlc(src, tickers, start, end)
        dividends = _fetch_cash_dividends(src, tickers, start, end)
        splits = _fetch_splits(src, tickers, start, end)
        fx_rates = _fetch_fx_rates(src, _currencies_for(tickers), start, end)
        fx_intraday_rates = _fetch_fx_intraday_rates(src, _currencies_for(tickers))

    try:
        bt = backtest(
            prices,
            req.weights,
            Plan(amount=req.plan.amount, frequency=req.plan.frequency),
            start,
            end,
            ohlc=ohlc,
            fx_rates=fx_rates,
            fx_intraday_rates=fx_intraday_rates,
            dividends=dividends,
            splits=splits,
            timeline_tz=user_tz if req.range == "today" else None,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return _backtest_response(
        bt, range_key=req.range, per_asset_status=per_asset_status,
        display_timezone=display_timezone,
    )
