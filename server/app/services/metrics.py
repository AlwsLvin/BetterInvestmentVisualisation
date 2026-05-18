from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass(frozen=True)
class AssetMetrics:
    annualized_roi: float
    max_drawdown: float
    drawdown_duration: float
    recovery_time: float
    volatility: float
    beta: float
    beta_benchmark: str | None = None
    dividend_yield: float | None = None


def daily_returns(prices: pd.Series) -> pd.Series:
    return prices.pct_change().dropna()


def annualized_return(prices: pd.Series) -> float:
    """Compound annual growth rate from first to last observation."""
    if len(prices) < 2:
        return 0.0
    p0, p1 = float(prices.iloc[0]), float(prices.iloc[-1])
    if p0 <= 0:
        return 0.0
    days = (prices.index[-1] - prices.index[0]).days
    if days <= 0:
        return 0.0
    years = days / 365.25
    return (p1 / p0) ** (1.0 / years) - 1.0


def max_drawdown_stats(prices: pd.Series) -> tuple[float, float, float]:
    """Return (mdd_magnitude, drawdown_duration_days, recovery_time_days).

    drawdown_duration spans peak -> recovery (full underwater window).
    recovery_time spans trough -> recovery (climb-back portion).
    If the series never recovers from the worst trough, both metrics are
    measured to the end of the series (still underwater).
    """
    if len(prices) < 2:
        return 0.0, 0.0, 0.0

    cummax = prices.cummax()
    drawdown = prices / cummax - 1.0
    trough_pos = int(drawdown.values.argmin())
    mdd = -float(drawdown.iloc[trough_pos])

    if mdd <= 0:
        return 0.0, 0.0, 0.0

    peak_value = float(cummax.iloc[trough_pos])
    peak_pos = int(np.argmax(prices.values[: trough_pos + 1] >= peak_value))
    after_trough = prices.iloc[trough_pos:]
    recovered = after_trough[after_trough >= peak_value]
    if len(recovered) > 0:
        recovery_pos_in_full = prices.index.get_loc(recovered.index[0])
    else:
        recovery_pos_in_full = len(prices) - 1

    peak_date = prices.index[peak_pos]
    trough_date = prices.index[trough_pos]
    recovery_date = prices.index[recovery_pos_in_full]
    drawdown_duration = float((recovery_date - peak_date).days)
    recovery_time = float((recovery_date - trough_date).days)
    return mdd, drawdown_duration, recovery_time


def volatility(prices: pd.Series, trading_days: int = TRADING_DAYS) -> float:
    """Annualized stdev of daily simple returns."""
    r = daily_returns(prices)
    if len(r) < 2:
        return 0.0
    return float(r.std(ddof=1) * np.sqrt(trading_days))


def beta(asset_prices: pd.Series, benchmark_prices: pd.Series) -> float:
    """Cov(R_a, R_b) / Var(R_b) on daily returns over the overlap window.

    Computed locally because price-data APIs (yfinance, etc.) do not return
    historical beta time series.
    """
    aligned = pd.concat([asset_prices, benchmark_prices], axis=1, join="inner").dropna()
    if len(aligned) < 3:
        return 1.0
    a = aligned.iloc[:, 0].pct_change().dropna()
    b = aligned.iloc[:, 1].pct_change().dropna()
    common = a.index.intersection(b.index)
    a, b = a.loc[common], b.loc[common]
    var_b = float(b.var(ddof=1))
    if var_b <= 0:
        return 1.0
    cov_ab = float(np.cov(a.values, b.values, ddof=1)[0, 1])
    return cov_ab / var_b


def dividend_yield(
    prices: pd.Series,
    dividends: pd.Series | None,
    lookback_days: int = 365,
) -> float | None:
    """Trailing dividend yield over the lookback window.

    Returns None when ``dividends`` is None (yfinance may not provide them).
    Sum of dividend cash over the trailing window divided by current price.
    """
    if dividends is None or len(dividends) == 0 or len(prices) == 0:
        return None
    end = prices.index[-1]
    start = end - pd.Timedelta(days=lookback_days)
    window = dividends[(dividends.index >= start) & (dividends.index <= end)]
    total = float(window.sum())
    last_price = float(prices.iloc[-1])
    if last_price <= 0:
        return None
    return total / last_price


def compute_asset_metrics(
    prices: pd.Series,
    benchmark_prices: pd.Series,
    dividends: pd.Series | None = None,
    beta_benchmark: str | None = None,
) -> AssetMetrics:
    mdd, dd_dur, rec = max_drawdown_stats(prices)
    return AssetMetrics(
        annualized_roi=annualized_return(prices),
        max_drawdown=mdd,
        drawdown_duration=dd_dur,
        recovery_time=rec,
        volatility=volatility(prices),
        beta=beta(prices, benchmark_prices),
        beta_benchmark=beta_benchmark,
        dividend_yield=dividend_yield(prices, dividends),
    )


def compute_metrics(
    prices: Mapping[str, pd.Series],
    benchmark_prices: pd.Series,
    dividends: Mapping[str, pd.Series] | None = None,
) -> dict[str, AssetMetrics]:
    out: dict[str, AssetMetrics] = {}
    for ticker, series in prices.items():
        div = dividends.get(ticker) if dividends else None
        out[ticker] = compute_asset_metrics(series, benchmark_prices, div)
    return out


def compute_metrics_by_benchmark(
    prices: Mapping[str, pd.Series],
    benchmark_prices: Mapping[str, pd.Series],
    dividends: Mapping[str, pd.Series] | None = None,
    beta_benchmarks: Mapping[str, str] | None = None,
) -> dict[str, AssetMetrics]:
    out: dict[str, AssetMetrics] = {}
    for ticker, series in prices.items():
        div = dividends.get(ticker) if dividends else None
        benchmark = benchmark_prices[ticker]
        out[ticker] = compute_asset_metrics(
            series,
            benchmark,
            div,
            beta_benchmark=beta_benchmarks.get(ticker) if beta_benchmarks else None,
        )
    return out


def metrics_to_decision_rows(
    metrics: Mapping[str, AssetMetrics],
    indicator_names: Sequence[str],
) -> list[list[float]]:
    """Materialize a crisp decision matrix in the order of ``indicator_names``.

    The fuzzification step (TFN construction) is left to the allocation
    pipeline so it can attach uncertainty bands derived from rolling stdev.
    """
    rows: list[list[float]] = []
    for ticker, m in metrics.items():
        row = []
        for name in indicator_names:
            value = getattr(m, name)
            if value is None:
                raise ValueError(f"{ticker} missing indicator {name}")
            row.append(float(value))
        rows.append(row)
    return rows
