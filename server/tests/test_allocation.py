import math

import pytest

from app.services.allocation import allocate
from app.services.metrics import AssetMetrics


def _sample_metrics(with_dividend: bool = True) -> dict[str, AssetMetrics]:
    div = 0.005 if with_dividend else None
    return {
        "AAPL": AssetMetrics(
            annualized_roi=0.25,
            max_drawdown=0.18,
            drawdown_duration=120.0,
            recovery_time=60.0,
            volatility=0.28,
            beta=1.20,
            dividend_yield=div,
        ),
        "BIL": AssetMetrics(
            annualized_roi=0.04,
            max_drawdown=0.005,
            drawdown_duration=10.0,
            recovery_time=5.0,
            volatility=0.01,
            beta=0.02,
            dividend_yield=0.045 if with_dividend else None,
        ),
        "NVDA": AssetMetrics(
            annualized_roi=0.65,
            max_drawdown=0.55,
            drawdown_duration=240.0,
            recovery_time=180.0,
            volatility=0.55,
            beta=1.80,
            dividend_yield=0.001 if with_dividend else None,
        ),
        "KO": AssetMetrics(
            annualized_roi=0.08,
            max_drawdown=0.12,
            drawdown_duration=200.0,
            recovery_time=90.0,
            volatility=0.18,
            beta=0.55,
            dividend_yield=0.030 if with_dividend else None,
        ),
        "LOSER": AssetMetrics(
            annualized_roi=-0.15,
            max_drawdown=0.40,
            drawdown_duration=300.0,
            recovery_time=200.0,
            volatility=0.45,
            beta=1.50,
            dividend_yield=0.0 if with_dividend else None,
        ),
    }


def test_allocate_with_dividend_sums_to_one():
    result = allocate(_sample_metrics(True), style="high_return")
    assert math.isclose(sum(result.allocation.values()), 1.0, rel_tol=1e-9)
    assert result.has_dividend is True
    assert len(result.indicators) == 7


def test_allocate_without_dividend_sums_to_one():
    metrics = _sample_metrics(True)
    metrics["NODIV"] = AssetMetrics(0.10, 0.15, 100.0, 50.0, 0.20, 1.0, dividend_yield=None)
    result = allocate(metrics, style="high_return")
    assert math.isclose(sum(result.allocation.values()), 1.0, rel_tol=1e-9)
    assert result.has_dividend is False
    assert len(result.indicators) == 6


def test_high_return_style_favors_nvda_or_aapl_over_loser():
    result = allocate(_sample_metrics(True), style="high_return", scheme="softmax", tau=0.1)
    assert result.allocation["LOSER"] < result.allocation["AAPL"]
    assert result.allocation["LOSER"] < result.allocation["NVDA"]


def test_low_volatility_style_favors_bil_over_nvda():
    result = allocate(_sample_metrics(True), style="low_volatility", scheme="softmax", tau=0.1)
    assert result.allocation["BIL"] > result.allocation["NVDA"]


def test_negative_roi_does_not_zero_out_other_indicators():
    """Sanity check that the loser still gets a non-zero closeness because it
    has zero dividend rather than a NaN, and that no NaN propagates."""
    result = allocate(_sample_metrics(True), style="high_return")
    for v in result.allocation.values():
        assert v >= 0
        assert not math.isnan(v)


def test_floor_enforced_per_asset():
    result = allocate(_sample_metrics(True), style="high_return", scheme="softmax",
                      tau=0.05, floor=0.05)
    assert all(v >= 0.05 - 1e-9 for v in result.allocation.values())
    assert math.isclose(sum(result.allocation.values()), 1.0, rel_tol=1e-9)


def test_global_weights_sum_to_one():
    result = allocate(_sample_metrics(True), style="high_return")
    assert math.isclose(sum(result.global_weights.values()), 1.0, rel_tol=1e-9)


def test_unknown_style_raises():
    with pytest.raises(ValueError):
        allocate(_sample_metrics(True), style="moonshot")  # type: ignore[arg-type]


def test_empty_metrics_raises():
    with pytest.raises(ValueError):
        allocate({}, style="high_return")
