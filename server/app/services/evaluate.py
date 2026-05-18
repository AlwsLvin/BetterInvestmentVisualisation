from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from app.data.symbols import currency_of
from app.services.backtest import _as_ohlc_frame, _fx_rate
from app.services.metrics import TRADING_DAYS, annualized_return

RISK_FREE_PROXY_TICKER = "BIL.US"


@dataclass(frozen=True)
class PortfolioEvaluation:
    cumulative_return: float
    annualized_return: float
    volatility: float            # annualized stdev of daily portfolio returns
    max_drawdown: float
    beta: float | None           # portfolio beta vs benchmark (regression)
    alpha: float | None          # Jensen's alpha, annualized
    sharpe: float                # (R_p - R_f) / sigma_p
    rf_used: float               # the risk-free rate actually applied (annualized)
    rf_source: str               # "bil_default" | "override" | "constant_fallback"


def _portfolio_close_series(
    prices: Mapping[str, pd.Series],
    weights: Mapping[str, float],
    ohlc: Mapping[str, pd.DataFrame] | None = None,
    fx_rates: Mapping[str, pd.Series | pd.DataFrame] | None = None,
) -> pd.Series:
    """Daily portfolio close, normalized so that the first overlap day = 1.0.

    Computed by holding the implied share counts purchased at t=0 with the
    given weights — i.e. a buy-and-hold portfolio. Adjusted-close prices
    bake in dividend reinvestment, so this is a total-return series.
    """
    close_sources = {}
    open_sources = {}
    for t in weights:
        frame = _as_ohlc_frame(ohlc[t]) if ohlc and t in ohlc else _as_ohlc_frame(prices[t])
        close_sources[t] = frame["Close"]
        open_sources[t] = frame["Open"]

    close_df = pd.concat(close_sources, axis=1).sort_index().ffill().dropna(how="any")
    if close_df.empty:
        raise ValueError("no overlapping price data across the portfolio")
    open_df = pd.concat(open_sources, axis=1).sort_index().reindex(close_df.index)
    base_day = close_df.index[0]

    norm_parts = {}
    for t in weights:
        currency = currency_of(t)
        base_open = float(open_df.at[base_day, t])
        if not np.isfinite(base_open) or base_open <= 0:
            base_open = float(close_df.at[base_day, t])
        base_fx = _fx_rate(currency, base_day, fx_rates, "Open")
        if base_fx is None:
            raise ValueError(f"missing FX rate for {currency}")
        base_usd = base_open / base_fx

        values = []
        for d, close_local in close_df[t].items():
            fx_close = _fx_rate(currency, d, fx_rates, "Close")
            if fx_close is None or base_usd <= 0:
                values.append(np.nan)
            else:
                values.append(float(close_local) / fx_close / base_usd)
        norm_parts[t] = pd.Series(values, index=close_df.index)

    norm = pd.concat(norm_parts, axis=1).dropna(how="any")
    if norm.empty:
        raise ValueError("no overlapping USD-normalized price data across the portfolio")
    series = norm.mul(pd.Series(weights), axis=1).sum(axis=1)
    series.name = "portfolio"
    return series


def _max_drawdown(curve: pd.Series) -> float:
    if len(curve) < 2:
        return 0.0
    running_max = curve.cummax()
    dd = curve / running_max - 1.0
    return float(-dd.min())


def _safe_annualized(total_multiple: float, start, end) -> float:
    """CAGR with same-day/intraday overflow protection."""
    if not np.isfinite(total_multiple) or total_multiple <= 0:
        return 0.0
    days = (end - start).days
    if days <= 0:
        return float(total_multiple - 1.0)
    years = days / 365.25
    try:
        annual = total_multiple ** (1.0 / years) - 1.0
    except OverflowError:
        return float(total_multiple - 1.0)
    if not np.isfinite(annual):
        return float(total_multiple - 1.0)
    return float(annual)


def _bil_annual_return(prices: Mapping[str, pd.Series]) -> float | None:
    bil = prices.get(RISK_FREE_PROXY_TICKER)
    if bil is None or len(bil) < 2:
        return None
    return annualized_return(bil)


def evaluate_portfolio(
    prices: Mapping[str, pd.Series],
    weights: Mapping[str, float],
    benchmark_prices: pd.Series | None,
    rf_override: float | None = None,
    rf_default: float | None = None,
    ohlc: Mapping[str, pd.DataFrame] | None = None,
    fx_rates: Mapping[str, pd.Series | pd.DataFrame] | None = None,
) -> PortfolioEvaluation:
    """Classic CAPM-style evaluation of a buy-and-hold weighted portfolio."""

    if not weights:
        raise ValueError("empty weights")
    if abs(sum(weights.values()) - 1.0) > 1e-3:
        raise ValueError(f"weights must sum to 1, got {sum(weights.values()):.6f}")

    series = _portfolio_close_series(prices, weights, ohlc=ohlc, fx_rates=fx_rates)
    cumulative_return = float(series.iloc[-1] - 1.0)
    annual = _safe_annualized(float(series.iloc[-1]), series.index[0], series.index[-1])
    series_ret = series.pct_change().dropna()
    sigma = (
        float(series_ret.std(ddof=1) * np.sqrt(TRADING_DAYS))
        if len(series_ret) >= 2 else 0.0
    )
    mdd = _max_drawdown(series)

    if rf_override is not None:
        rf = float(rf_override)
        rf_source = "override"
    elif rf_default is not None:
        rf = float(rf_default)
        rf_source = "bil_default"
    else:
        bil = _bil_annual_return(prices)
        if bil is not None:
            rf = float(bil)
            rf_source = "bil_default"
        else:
            rf = 0.03
            rf_source = "constant_fallback"

    beta_value: float | None = None
    alpha: float | None = None
    if benchmark_prices is not None and len(benchmark_prices) >= 3:
        aligned = pd.concat([series, benchmark_prices], axis=1, join="inner").dropna()
        if len(aligned) >= 3:
            p_ret = aligned.iloc[:, 0].pct_change().dropna()
            b_ret = aligned.iloc[:, 1].pct_change().dropna()
            common = p_ret.index.intersection(b_ret.index)
            p_ret, b_ret = p_ret.loc[common], b_ret.loc[common]
            var_b = float(b_ret.var(ddof=1)) if len(b_ret) >= 2 else 0.0
            if var_b > 0 and len(p_ret) >= 2:
                beta_value = float(np.cov(p_ret.values, b_ret.values, ddof=1)[0, 1] / var_b)
                bench_total = float(aligned.iloc[-1, 1] / aligned.iloc[0, 1])
                bench_annual = _safe_annualized(bench_total, aligned.index[0], aligned.index[-1])
                alpha = float(annual - (rf + beta_value * (bench_annual - rf)))
    sharpe = (annual - rf) / sigma if sigma > 0 else 0.0

    return PortfolioEvaluation(
        cumulative_return=cumulative_return,
        annualized_return=float(annual),
        volatility=sigma,
        max_drawdown=mdd,
        beta=beta_value,
        alpha=alpha,
        sharpe=float(sharpe),
        rf_used=rf,
        rf_source=rf_source,
    )
