import math

import numpy as np
import pandas as pd
import pytest

from app.services.metrics import (
    annualized_return,
    beta,
    compute_metrics,
    dividend_yield,
    max_drawdown_stats,
    volatility,
)


def _series(values: list[float], start: str = "2024-01-01", freq: str = "B") -> pd.Series:
    idx = pd.date_range(start=start, periods=len(values), freq=freq)
    return pd.Series(values, index=idx, dtype=float)


def test_annualized_return_doubling_in_one_year():
    s = _series([100.0, 200.0])
    s.index = pd.DatetimeIndex(["2024-01-01", "2025-01-01"])
    r = annualized_return(s)
    assert math.isclose(r, 1.0, rel_tol=5e-3)


def test_annualized_return_short_series_returns_zero():
    assert annualized_return(_series([100.0])) == 0.0


def test_max_drawdown_simple():
    s = _series([100, 110, 80, 90, 120])
    mdd, dd_dur, rec = max_drawdown_stats(s)
    assert math.isclose(mdd, (110 - 80) / 110, rel_tol=1e-9)
    assert dd_dur > 0
    assert rec >= 0


def test_max_drawdown_no_drawdown_zero():
    s = _series([100, 110, 120, 130])
    mdd, dd_dur, rec = max_drawdown_stats(s)
    assert mdd == 0.0
    assert dd_dur == 0.0
    assert rec == 0.0


def test_volatility_flat_series_is_zero():
    s = _series([100.0] * 30)
    assert volatility(s) == 0.0


def test_volatility_positive_for_varying_series():
    rng = np.random.default_rng(0)
    s = _series(list(100 + rng.standard_normal(252).cumsum()))
    assert volatility(s) > 0


def test_beta_identical_series_is_one():
    rng = np.random.default_rng(1)
    base = pd.Series(100 + rng.standard_normal(100).cumsum(),
                     index=pd.date_range("2024-01-01", periods=100, freq="B"))
    assert math.isclose(beta(base, base), 1.0, rel_tol=1e-9)


def test_beta_uncorrelated_series_near_zero():
    rng = np.random.default_rng(2)
    idx = pd.date_range("2024-01-01", periods=500, freq="B")
    a = pd.Series(100 + rng.standard_normal(500).cumsum(), index=idx)
    b = pd.Series(100 + rng.standard_normal(500).cumsum(), index=idx)
    assert abs(beta(a, b)) < 0.5


def test_dividend_yield_none_when_dividends_none():
    s = _series([100.0, 101.0])
    assert dividend_yield(s, None) is None


def test_dividend_yield_sum_over_window():
    prices = pd.Series([100.0] * 250,
                       index=pd.date_range("2024-01-01", periods=250, freq="B"))
    div_idx = pd.DatetimeIndex(["2024-03-01", "2024-06-01", "2024-09-01"])
    dividends = pd.Series([0.5, 0.5, 0.5], index=div_idx)
    y = dividend_yield(prices, dividends, lookback_days=365)
    assert math.isclose(y, 1.5 / 100.0, rel_tol=1e-9)


def test_compute_metrics_aggregates_per_ticker():
    idx = pd.date_range("2024-01-01", periods=300, freq="B")
    prices = {
        "A": pd.Series(np.linspace(100, 130, 300), index=idx),
        "B": pd.Series(np.linspace(100, 90, 300), index=idx),
    }
    benchmark = pd.Series(np.linspace(100, 110, 300), index=idx)
    metrics = compute_metrics(prices, benchmark)
    assert set(metrics.keys()) == {"A", "B"}
    assert metrics["A"].annualized_roi > metrics["B"].annualized_roi
    assert metrics["A"].dividend_yield is None
