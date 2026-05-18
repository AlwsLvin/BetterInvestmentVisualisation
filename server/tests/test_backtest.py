import math
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from app.services.backtest import (
    Plan,
    _frequency_to_invest_dates,
    _fx_rate,
    _irr,
    _max_drawdown,
    backtest,
)


def _bd_index(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=periods)


def test_invest_dates_daily_matches_business_days():
    idx = _bd_index("2024-01-02", 20)
    dates = _frequency_to_invest_dates(
        date(2024, 1, 1), date(2024, 1, 31), "daily", idx
    )
    assert len(dates) == len(idx)
    assert dates[0] == idx[0]


def test_invest_dates_weekly_returns_one_per_week():
    idx = _bd_index("2024-01-01", 60)
    dates = _frequency_to_invest_dates(
        date(2024, 1, 1), date(2024, 3, 1), "weekly:MON", idx
    )
    assert 7 <= len(dates) <= 10
    for d in dates:
        assert d in idx


def test_invest_dates_monthly_15_includes_head_then_15ths():
    idx = pd.bdate_range("2024-01-01", "2024-12-31")
    dates = _frequency_to_invest_dates(
        date(2024, 1, 1), date(2024, 12, 31), "monthly:15", idx
    )
    assert len(dates) == 13
    assert dates[0] == idx[0]
    for d in dates[1:]:
        assert d.day >= 15


def test_first_invest_date_is_always_start_for_any_frequency():
    idx = pd.bdate_range("2024-01-01", "2024-12-31")
    for freq in ["daily", "weekly:MON", "monthly:15", "every:30d"]:
        dates = _frequency_to_invest_dates(
            date(2024, 1, 1), date(2024, 12, 31), freq, idx
        )
        assert dates[0] == idx[0], f"freq={freq} did not seed head buy"


def test_invest_dates_every_30d():
    idx = pd.bdate_range("2024-01-01", "2024-12-31")
    dates = _frequency_to_invest_dates(
        date(2024, 1, 1), date(2024, 12, 31), "every:30d", idx
    )
    assert 11 <= len(dates) <= 13
    for d in dates:
        assert d in idx


def test_invest_dates_unknown_frequency_raises():
    idx = _bd_index("2024-01-01", 10)
    with pytest.raises(ValueError):
        _frequency_to_invest_dates(date(2024, 1, 1), date(2024, 1, 10), "yearly", idx)


def test_irr_simple_doubling_in_one_year():
    # Invest 100 at t=0, get 200 back at t=365 -> IRR = 100%
    r = _irr([-100.0, 200.0], [0, 365])
    assert r is not None
    assert math.isclose(r, 1.0, rel_tol=1e-3)


def test_irr_zero_when_no_growth():
    r = _irr([-100.0, 100.0], [0, 365])
    assert r is not None
    assert abs(r) < 1e-3


def test_irr_returns_none_for_all_outflows():
    assert _irr([-100.0, -50.0], [0, 30]) is None


def test_max_drawdown_simple():
    curve = np.array([1.0, 1.2, 0.8, 0.9, 1.5])
    dd = _max_drawdown(curve)
    assert math.isclose(dd, (1.2 - 0.8) / 1.2)


def test_max_drawdown_no_drawdown():
    assert _max_drawdown(np.array([1.0, 1.1, 1.2])) == 0.0


def _flat_prices(ticker: str, start: str, days: int, value: float = 100.0) -> pd.Series:
    idx = pd.bdate_range(start, periods=days)
    return pd.Series([value] * days, index=idx, name=ticker)


def _linear_prices(ticker: str, start: str, days: int, p0: float, p1: float) -> pd.Series:
    idx = pd.bdate_range(start, periods=days)
    return pd.Series(np.linspace(p0, p1, days), index=idx, name=ticker)


def test_backtest_flat_prices_yields_zero_return():
    prices = {"A": _flat_prices("A", "2024-01-02", 250)}
    result = backtest(
        prices,
        {"A": 1.0},
        Plan(amount=100.0, frequency="monthly:1"),
        date(2024, 1, 1),
        date(2024, 12, 31),
    )
    assert math.isclose(result.cumulative_return, 0.0, abs_tol=1e-9)
    assert math.isclose(result.final_nav, result.total_invested, rel_tol=1e-9)


def test_backtest_doubling_lump_sum_yields_double():
    prices = {"A": _linear_prices("A", "2024-01-02", 252, 100.0, 200.0)}
    result = backtest(
        prices,
        {"A": 1.0},
        Plan(amount=1000.0, frequency="every:5000d"),
        date(2024, 1, 1),
        date(2024, 12, 31),
    )
    assert len(result.invest_dates) == 1
    assert math.isclose(result.cumulative_return, 1.0, rel_tol=1e-3)
    assert math.isclose(result.final_nav, 2 * result.total_invested, rel_tol=1e-3)


def test_backtest_dca_into_rising_market_lower_than_lumpsum():
    """DCA into a monotonically rising market always trails a lump-sum."""
    prices = {"A": _linear_prices("A", "2024-01-02", 252, 100.0, 200.0)}
    dca = backtest(prices, {"A": 1.0}, Plan(100.0, "monthly:1"),
                   date(2024, 1, 1), date(2024, 12, 31))
    lump = backtest(prices, {"A": 1.0}, Plan(1200.0, "every:5000d"),
                    date(2024, 1, 1), date(2024, 12, 31))
    assert dca.cumulative_return < lump.cumulative_return


def test_backtest_weights_must_sum_to_one():
    prices = {"A": _flat_prices("A", "2024-01-02", 100)}
    with pytest.raises(ValueError):
        backtest(prices, {"A": 0.5}, Plan(100.0), date(2024, 1, 1), date(2024, 6, 1))


def test_backtest_missing_ticker_raises():
    prices = {"A": _flat_prices("A", "2024-01-02", 100)}
    with pytest.raises(ValueError):
        backtest(prices, {"A": 0.5, "B": 0.5}, Plan(100.0),
                 date(2024, 1, 1), date(2024, 6, 1))


def test_backtest_per_asset_final_value_sums_to_nav():
    prices = {
        "A": _linear_prices("A", "2024-01-02", 252, 100.0, 150.0),
        "B": _linear_prices("B", "2024-01-02", 252, 100.0, 200.0),
    }
    result = backtest(
        prices, {"A": 0.4, "B": 0.6}, Plan(100.0, "monthly:1"),
        date(2024, 1, 1), date(2024, 12, 31),
    )
    total_per_asset = sum(result.per_asset_final_value.values())
    assert math.isclose(
        total_per_asset + result.cash_left["USD"],
        result.final_nav,
        rel_tol=1e-9,
    )


def test_backtest_dates_and_nav_aligned():
    prices = {"A": _flat_prices("A", "2024-01-02", 100)}
    result = backtest(prices, {"A": 1.0}, Plan(100.0, "monthly:1"),
                      date(2024, 1, 1), date(2024, 12, 31))
    assert len(result.dates) == len(result.nav) == len(result.cash_invested)
    assert len(result.return_pct) == len(result.dates)


def test_backtest_sorts_unsorted_price_input():
    ascending = _linear_prices("A", "2024-01-02", 20, 100.0, 120.0)
    descending = ascending.sort_index(ascending=False)
    result = backtest({"A": descending}, {"A": 1.0}, Plan(100.0, "weekly:MON"),
                      date(2024, 1, 1), date(2024, 2, 1))
    assert result.dates == sorted(result.dates)
    assert result.dates[0] < result.dates[-1]


def test_backtest_buys_integer_shares_and_keeps_cash_left():
    idx = pd.bdate_range("2024-01-02", periods=1)
    prices = {"AAPL.US": pd.Series([1.3], index=idx, name="AAPL.US")}
    result = backtest(
        prices,
        {"AAPL.US": 1.0},
        Plan(10.0, "every:5000d"),
        date(2024, 1, 1),
        date(2024, 1, 31),
    )
    assert math.isclose(result.per_asset_final_value["AAPL.US"], 9.1)
    assert math.isclose(result.cash_left["USD"], 0.9)
    assert math.isclose(result.final_nav, 10.0)


def test_backtest_uses_open_for_buy_and_close_for_nav():
    idx = pd.bdate_range("2024-01-02", periods=1)
    prices = {"AAPL.US": pd.Series([110.0], index=idx, name="AAPL.US")}
    ohlc = {"AAPL.US": pd.DataFrame({
        "Open": [100.0], "High": [112.0], "Low": [99.0], "Close": [110.0],
    }, index=idx)}
    result = backtest(
        prices,
        {"AAPL.US": 1.0},
        Plan(1000.0, "every:5000d"),
        date(2024, 1, 1),
        date(2024, 1, 31),
        ohlc=ohlc,
    )
    assert math.isclose(result.return_pct[0], 0.1)
    assert math.isclose(result.final_nav, 1100.0)


def test_backtest_a_share_lot_blocks_small_order():
    idx = pd.bdate_range("2024-01-02", periods=1)
    prices = {"600519.SS": pd.Series([10.0], index=idx, name="600519.SS")}
    fx = {"CNY": pd.DataFrame({"Open": [7.0], "Close": [7.0]}, index=idx)}
    result = backtest(
        prices,
        {"600519.SS": 1.0},
        Plan(100.0, "every:5000d"),
        date(2024, 1, 1),
        date(2024, 1, 31),
        fx_rates=fx,
    )
    assert result.per_asset_final_value["600519.SS"] == 0.0
    assert result.cash_left["USD"] == 100.0


def test_backtest_converts_cny_lot_cost_to_usd():
    idx = pd.bdate_range("2024-01-02", periods=1)
    prices = {"600519.SS": pd.Series([7.0], index=idx, name="600519.SS")}
    fx = {"CNY": pd.DataFrame({"Open": [7.0], "Close": [7.0]}, index=idx)}
    result = backtest(
        prices,
        {"600519.SS": 1.0},
        Plan(100.0, "every:5000d"),
        date(2024, 1, 1),
        date(2024, 1, 31),
        fx_rates=fx,
    )
    assert math.isclose(result.per_asset_final_value["600519.SS"], 100.0)
    assert math.isclose(result.cash_left["USD"], 0.0)


def test_daily_backtest_uses_fx_open_for_cost_and_fx_close_for_nav():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-05-07")])
    prices = {"600519.SS": pd.Series([14.0], index=idx, name="600519.SS")}
    ohlc = {"600519.SS": pd.DataFrame({
        "Open": [7.0], "High": [14.0], "Low": [7.0], "Close": [14.0],
    }, index=idx)}
    fx = {"CNY": pd.DataFrame({
        "Open": [7.0], "Close": [14.0],
    }, index=idx)}
    result = backtest(
        prices,
        {"600519.SS": 1.0},
        Plan(100.0, "every:5000d"),
        date(2026, 5, 7),
        date(2026, 5, 7),
        ohlc=ohlc,
        fx_rates=fx,
    )
    event = result.purchase_events[0]
    assert event.fx_source == "daily_fallback"
    assert math.isclose(event.fx_rate, 7.0)
    assert math.isclose(event.shares, 100.0)
    assert math.isclose(result.final_nav, 100.0)


def test_hk_purchase_event_uses_intraday_fx_asof_at_market_open():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-05-07")])
    prices = {"1398.HK": pd.Series([5.0], index=idx, name="1398.HK")}
    ohlc = {"1398.HK": pd.DataFrame({
        "Open": [4.0], "High": [5.2], "Low": [3.9], "Close": [5.0],
    }, index=idx)}
    daily_fx = {"HKD": pd.DataFrame({
        "Open": [7.833849906921387], "Close": [7.834080219268799],
    }, index=idx)}
    fx_ticks = {"HKD": pd.DataFrame({
        "Close": [7.7, 7.9],
        "_bar_minutes": [5, 5],
        "_fx_source": ["minute_asof", "minute_asof"],
    },
        index=pd.DatetimeIndex([
            "2026-05-07 09:25",
            "2026-05-07 09:30",
        ], tz="Asia/Hong_Kong"),
    )}
    result = backtest(
        prices,
        {"1398.HK": 1.0},
        Plan(1000.0, "every:5000d"),
        date(2026, 5, 7),
        date(2026, 5, 7),
        ohlc=ohlc,
        fx_rates=daily_fx,
        fx_intraday_rates=fx_ticks,
    )
    event = result.purchase_events[0]
    assert event.purchased_at == datetime(2026, 5, 7, 9, 30)
    assert event.purchased_at_timezone == "Asia/Hong_Kong"
    assert event.fx_source == "minute_asof"
    assert math.isclose(event.fx_rate, 7.7)
    assert pd.Timestamp(event.fx_as_of).tz_convert("Asia/Hong_Kong").minute == 25


def test_hourly_fx_bar_close_after_open_does_not_leak_future_rate():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-05-07")])
    prices = {"1398.HK": pd.Series([5.0], index=idx, name="1398.HK")}
    ohlc = {"1398.HK": pd.DataFrame({
        "Open": [4.0], "High": [5.2], "Low": [3.9], "Close": [5.0],
    }, index=idx)}
    daily_fx = {"HKD": pd.DataFrame({
        "Open": [7.833849906921387], "Close": [7.834080219268799],
    }, index=idx)}
    fx_ticks = {"HKD": pd.DataFrame({
        "Close": [7.7, 7.9],
        "_bar_minutes": [60, 60],
        "_fx_source": ["hourly_approx", "hourly_approx"],
    }, index=pd.DatetimeIndex([
        "2026-05-07 09:00",
        "2026-05-07 10:00",
    ], tz="Asia/Hong_Kong"))}
    result = backtest(
        prices,
        {"1398.HK": 1.0},
        Plan(1000.0, "every:5000d"),
        date(2026, 5, 7),
        date(2026, 5, 7),
        ohlc=ohlc,
        fx_rates=daily_fx,
        fx_intraday_rates=fx_ticks,
    )
    event = result.purchase_events[0]
    assert event.fx_source == "daily_fallback"
    assert math.isclose(event.fx_rate, 7.833849906921387)


def test_hk_purchase_event_marks_daily_fx_fallback_when_intraday_missing():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-05-07")])
    prices = {"1398.HK": pd.Series([5.0], index=idx, name="1398.HK")}
    ohlc = {"1398.HK": pd.DataFrame({
        "Open": [4.0], "High": [5.2], "Low": [3.9], "Close": [5.0],
    }, index=idx)}
    daily_fx = {"HKD": pd.DataFrame({
        "Open": [7.833849906921387], "Close": [7.834080219268799],
    }, index=idx)}
    result = backtest(
        prices,
        {"1398.HK": 1.0},
        Plan(1000.0, "every:5000d"),
        date(2026, 5, 7),
        date(2026, 5, 7),
        ohlc=ohlc,
        fx_rates=daily_fx,
    )
    event = result.purchase_events[0]
    assert event.fx_source == "daily_fallback"
    assert math.isclose(event.fx_rate, 7.833849906921387)
    assert event.fx_as_of == date(2026, 5, 7)
    assert event.fx_alignment_note


def test_fx_rate_uses_asof_without_future_intraday_tick():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-05-11 10:00")])
    fx = {"CNY": pd.Series([7.0], index=idx, name="CNY")}
    assert _fx_rate("CNY", pd.Timestamp("2026-05-11 09:30"), fx, "Close") is None
    assert math.isclose(
        _fx_rate("CNY", pd.Timestamp("2026-05-11 10:05"), fx, "Close"),
        7.0,
    )


def test_today_backtest_does_not_backfill_future_market_price():
    us_tick = pd.Timestamp("2026-05-09 04:00")
    cn_tick = pd.Timestamp("2026-05-11 09:30")
    prices = {
        "AAPL.US": pd.Series([100.0], index=pd.DatetimeIndex([us_tick]), name="AAPL.US"),
        "600519.SS": pd.Series([7.0], index=pd.DatetimeIndex([cn_tick]), name="600519.SS"),
    }
    fx = {
        "CNY": pd.Series(
            [7.0],
            index=pd.DatetimeIndex([us_tick]),
            name="CNY",
        ),
    }
    fx["CNY"].attrs["bar_minutes"] = 5
    fx["CNY"].attrs["fx_source"] = "minute_asof"
    result = backtest(
        prices,
        {"AAPL.US": 0.5, "600519.SS": 0.5},
        Plan(1000.0, "daily"),
        date(2026, 5, 9),
        date(2026, 5, 11),
        fx_rates=fx,
    )
    assert result.dates == [us_tick, cn_tick]
    assert math.isclose(result.per_asset_final_value["AAPL.US"], 500.0)
    assert math.isclose(result.per_asset_final_value["600519.SS"], 500.0)
    assert math.isclose(result.final_nav, 1000.0)


def test_today_backtest_uses_intraday_open_for_purchase_price():
    tick = pd.Timestamp("2026-05-11 09:30")
    prices = {
        "AAPL.US": pd.Series([110.0], index=pd.DatetimeIndex([tick]), name="AAPL.US"),
    }
    ohlc = {
        "AAPL.US": pd.DataFrame({
            "Open": [100.0],
            "High": [112.0],
            "Low": [99.0],
            "Close": [110.0],
        }, index=pd.DatetimeIndex([tick])),
    }
    result = backtest(
        prices,
        {"AAPL.US": 1.0},
        Plan(1000.0, "daily"),
        date(2026, 5, 11),
        date(2026, 5, 11),
        ohlc=ohlc,
    )
    event = result.purchase_events[0]
    assert event.purchased_at == datetime(2026, 5, 11, 9, 30)
    assert event.price == 100.0
    assert math.isclose(result.return_pct[0], 0.1)


def test_today_backtest_fx_ticks_move_nav_while_stock_price_is_frozen():
    stock_tick = pd.Timestamp("2026-05-11 09:30")
    fx_tick = pd.Timestamp("2026-05-11 10:00")
    prices = {
        "600519.SS": pd.Series(
            [7.0],
            index=pd.DatetimeIndex([stock_tick]),
            name="600519.SS",
        ),
    }
    fx = {
        "CNY": pd.DataFrame({
            "Close": [7.0, 14.0],
            "_bar_minutes": [5, 5],
            "_fx_source": ["minute_asof", "minute_asof"],
        }, index=pd.DatetimeIndex([pd.Timestamp("2026-05-11 09:25"), fx_tick])),
    }
    result = backtest(
        prices,
        {"600519.SS": 1.0},
        Plan(100.0, "daily"),
        date(2026, 5, 11),
        date(2026, 5, 11),
        fx_rates=fx,
    )
    assert result.dates == [stock_tick, fx_tick]
    assert math.isclose(result.nav[0], 100.0)
    assert math.isclose(result.nav[1], 50.0)
    assert math.isclose(result.return_pct[-1], -0.5)


def test_backtest_cash_dividend_increases_cash_before_same_day_buy():
    idx = pd.bdate_range("2024-01-02", periods=2)
    prices = {"AAPL.US": pd.Series([10.0, 10.0], index=idx, name="AAPL.US")}
    dividends = {"AAPL.US": pd.Series([1.0], index=pd.DatetimeIndex([idx[1]]))}
    result = backtest(
        prices,
        {"AAPL.US": 1.0},
        Plan(1000.0, "every:5000d"),
        date(2024, 1, 2),
        date(2024, 1, 3),
        dividends=dividends,
    )
    assert math.isclose(result.final_nav, 1100.0)
    assert math.isclose(result.cash_left["USD"], 100.0)


def test_backtest_split_adjusts_existing_shares_before_valuation():
    idx = pd.bdate_range("2024-01-02", periods=2)
    prices = {"AAPL.US": pd.Series([10.0, 5.0], index=idx, name="AAPL.US")}
    splits = {"AAPL.US": pd.Series([2.0], index=pd.DatetimeIndex([idx[1]]))}
    result = backtest(
        prices,
        {"AAPL.US": 1.0},
        Plan(1000.0, "every:5000d"),
        date(2024, 1, 2),
        date(2024, 1, 3),
        splits=splits,
    )
    assert math.isclose(result.final_nav, 1000.0)
    assert math.isclose(result.per_asset_final_value["AAPL.US"], 1000.0)
