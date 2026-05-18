"""Mocked yfinance tests so the suite runs offline."""
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.data.base import DataSourceError
from app.data.cache import FileCache
from app.data.yfinance_source import YFinanceSource


def test_yfinance_source_sets_tz_cache_location(tmp_path):
    from app.data import yfinance_source as source_mod

    original = source_mod._YFINANCE_CACHE_CONFIGURED_FOR
    source_mod._YFINANCE_CACHE_CONFIGURED_FOR = None
    try:
        with patch("yfinance.set_tz_cache_location") as setter:
            YFinanceSource(cache=FileCache(tmp_path))
        expected = tmp_path / "yfinance"
        assert expected.is_dir()
        setter.assert_called_once_with(str(expected))
    finally:
        source_mod._YFINANCE_CACHE_CONFIGURED_FOR = original


def _fake_download_df() -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=5, freq="B", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open":  [100, 101, 102, 103, 104],
            "High":  [101, 102, 103, 104, 105],
            "Low":   [99,  100, 101, 102, 103],
            "Close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "Volume": [1_000_000] * 5,
        },
        index=idx,
    )


def _fake_intraday_download_df() -> pd.DataFrame:
    idx = pd.date_range(
        "2024-01-02 09:30", periods=4, freq="5min", tz="America/New_York"
    )[::-1]
    return pd.DataFrame(
        {
            "Open": [103, 102, 101, 100],
            "High": [104, 103, 102, 101],
            "Low": [102, 101, 100, 99],
            "Close": [103.5, 102.5, 101.5, 100.5],
            "Volume": [1_000_000] * 4,
        },
        index=idx,
    )


def test_get_prices_returns_close_tz_naive(tmp_path):
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.download", return_value=_fake_download_df()):
        prices = src.get_prices("AAPL.US", date(2024, 1, 1), date(2024, 1, 10))
    assert isinstance(prices, pd.Series)
    assert prices.index.tz is None
    assert list(prices.values) == [100.5, 101.5, 102.5, 103.5, 104.5]
    assert prices.name == "AAPL.US"


def test_get_prices_translates_symbol(tmp_path):
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.download", return_value=_fake_download_df()) as dl:
        src.get_prices("AAPL.US", date(2024, 1, 1), date(2024, 1, 10))
    args, kwargs = dl.call_args
    assert (args[0] if args else kwargs["tickers"]) == "AAPL"


def test_get_prices_passes_inclusive_end_to_yfinance(tmp_path):
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.download", return_value=_fake_download_df()) as dl:
        src.get_prices("AAPL.US", date(2024, 1, 1), date(2024, 1, 10))
    _, kwargs = dl.call_args
    assert kwargs["end"] == date(2024, 1, 11)


def test_get_prices_caches_result(tmp_path):
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.download", return_value=_fake_download_df()) as dl:
        src.get_prices("AAPL.US", date(2024, 1, 1), date(2024, 1, 10))
        src.get_prices("AAPL.US", date(2024, 1, 1), date(2024, 1, 10))
    assert dl.call_count == 1


def test_get_prices_sorts_cached_result(tmp_path):
    cache = FileCache(tmp_path)
    idx = pd.date_range("2024-01-02", periods=3, freq="B")[::-1]
    cache.set(
        "yf:px:v2:AAPL.US:2024-01-01:2024-01-10",
        pd.Series([3.0, 2.0, 1.0], index=idx, name="AAPL.US"),
    )
    src = YFinanceSource(cache=cache)
    prices = src.get_prices("AAPL.US", date(2024, 1, 1), date(2024, 1, 10))
    assert list(prices.index) == sorted(prices.index)


def test_get_prices_empty_raises(tmp_path):
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.download", return_value=pd.DataFrame()):
        with pytest.raises(DataSourceError):
            src.get_prices("AAPL.US", date(2024, 1, 1), date(2024, 1, 10))


def test_get_intraday_prices_returns_sorted_tz_naive_series(tmp_path):
    src = YFinanceSource(intraday_cache=FileCache(tmp_path, ttl_seconds=60))
    with patch("yfinance.download", return_value=_fake_intraday_download_df()) as dl:
        prices = src.get_intraday_prices("^GSPC")
    assert prices.index.tz is None
    assert list(prices.index) == sorted(prices.index)
    assert list(prices.values) == [100.5, 101.5, 102.5, 103.5]
    _, kwargs = dl.call_args
    assert kwargs["period"] == "1d"
    assert kwargs["interval"] == "5m"
    assert kwargs["threads"] is False


def test_get_intraday_prices_tz_preserves_source_timezone(tmp_path):
    src = YFinanceSource(intraday_cache=FileCache(tmp_path, ttl_seconds=60))
    with patch("yfinance.download", return_value=_fake_intraday_download_df()):
        prices = src.get_intraday_prices_tz("^GSPC")
    assert prices.index.tz is not None
    assert str(prices.index.tz) in {"America/New_York", "US/Eastern"}
    assert list(prices.index) == sorted(prices.index)


def test_get_intraday_ohlc_returns_open_close_sorted_tz_naive(tmp_path):
    src = YFinanceSource(intraday_cache=FileCache(tmp_path, ttl_seconds=60))
    with patch("yfinance.download", return_value=_fake_intraday_download_df()) as dl:
        frame = src.get_intraday_ohlc("^GSPC")
    assert frame.index.tz is None
    assert list(frame.index) == sorted(frame.index)
    assert list(frame["Open"]) == [100, 101, 102, 103]
    assert list(frame["Close"]) == [100.5, 101.5, 102.5, 103.5]
    _, kwargs = dl.call_args
    assert kwargs["period"] == "1d"
    assert kwargs["interval"] == "5m"


def test_get_intraday_ohlc_tz_preserves_source_timezone(tmp_path):
    src = YFinanceSource(intraday_cache=FileCache(tmp_path, ttl_seconds=60))
    with patch("yfinance.download", return_value=_fake_intraday_download_df()):
        frame = src.get_intraday_ohlc_tz("^GSPC")
    assert frame.index.tz is not None
    assert str(frame.index.tz) in {"America/New_York", "US/Eastern"}
    assert list(frame.index) == sorted(frame.index)


def test_get_intraday_ohlc_sorts_cached_result(tmp_path):
    cache = FileCache(tmp_path, ttl_seconds=60)
    idx = pd.date_range("2024-01-02 09:30", periods=3, freq="5min")[::-1]
    cache.set(
        "yf:intraday_ohlc:v1:^GSPC:1d:5m",
        pd.DataFrame({
            "Open": [3.0, 2.0, 1.0],
            "Close": [3.5, 2.5, 1.5],
        }, index=idx),
    )
    src = YFinanceSource(intraday_cache=cache)
    frame = src.get_intraday_ohlc("^GSPC")
    assert list(frame.index) == sorted(frame.index)
    assert list(frame["Open"]) == [1.0, 2.0, 3.0]


def test_get_intraday_prices_sorts_cached_result(tmp_path):
    cache = FileCache(tmp_path, ttl_seconds=60)
    idx = pd.date_range("2024-01-02 09:30", periods=3, freq="5min")[::-1]
    cache.set(
        "yf:intraday:v2:^GSPC:1d:5m",
        pd.Series([3.0, 2.0, 1.0], index=idx, name="^GSPC"),
    )
    src = YFinanceSource(intraday_cache=cache)
    prices = src.get_intraday_prices("^GSPC")
    assert list(prices.index) == sorted(prices.index)
    assert list(prices.values) == [1.0, 2.0, 3.0]


def test_get_intraday_prices_ignores_legacy_cache_key(tmp_path):
    cache = FileCache(tmp_path, ttl_seconds=60)
    cache.set(
        "yf:intraday:^GSPC:1d:5m",
        pd.Series([999.0], index=pd.date_range("2024-01-01 09:30", periods=1)),
    )
    src = YFinanceSource(intraday_cache=cache)
    with patch("yfinance.download", return_value=_fake_intraday_download_df()) as dl:
        prices = src.get_intraday_prices("^GSPC")
    assert dl.call_count == 1
    assert list(prices.values) == [100.5, 101.5, 102.5, 103.5]


def test_get_dividends_returns_series(tmp_path):
    div_idx = pd.DatetimeIndex(["2024-02-15", "2024-05-15"], tz="America/New_York")
    fake_divs = pd.Series([0.24, 0.25], index=div_idx)
    fake_ticker = MagicMock()
    fake_ticker.dividends = fake_divs
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.Ticker", return_value=fake_ticker):
        out = src.get_dividends("AAPL.US", date(2024, 1, 1), date(2024, 12, 31))
    assert out is not None
    assert out.index.tz is None
    assert list(out.values) == [0.24, 0.25]


def test_get_dividends_returns_none_when_empty(tmp_path):
    fake_ticker = MagicMock()
    fake_ticker.dividends = pd.Series(dtype=float)
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.Ticker", return_value=fake_ticker):
        assert src.get_dividends("BIL.US", date(2024, 1, 1), date(2024, 12, 31)) is None


def test_get_dividends_caches_none(tmp_path):
    fake_ticker = MagicMock()
    fake_ticker.dividends = pd.Series(dtype=float)
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.Ticker", return_value=fake_ticker) as t:
        src.get_dividends("X.US", date(2024, 1, 1), date(2024, 12, 31))
        src.get_dividends("X.US", date(2024, 1, 1), date(2024, 12, 31))
    assert t.call_count == 1


def test_get_ohlc_returns_dataframe(tmp_path):
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.download", return_value=_fake_download_df()):
        df = src.get_ohlc("AAPL.US", date(2024, 1, 1), date(2024, 1, 10))
    assert {"Open", "High", "Low", "Close"}.issubset(df.columns)
    assert len(df) == 5
    assert df.index.tz is None


def test_get_ohlc_passes_inclusive_end_to_yfinance(tmp_path):
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.download", return_value=_fake_download_df()) as dl:
        src.get_ohlc("AAPL.US", date(2024, 1, 1), date(2024, 1, 10))
    _, kwargs = dl.call_args
    assert kwargs["end"] == date(2024, 1, 11)


def test_get_raw_ohlc_uses_unadjusted_download(tmp_path):
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.Ticker") as ticker, patch(
        "yfinance.download", return_value=_fake_download_df(),
    ) as dl:
        ticker.return_value.splits = pd.Series(dtype=float)
        df = src.get_raw_ohlc("AAPL.US", date(2024, 1, 1), date(2024, 1, 10))
    _, kwargs = dl.call_args
    assert kwargs["auto_adjust"] is False
    assert kwargs["end"] == date(2024, 1, 11)
    assert {"Open", "High", "Low", "Close"}.issubset(df.columns)


def test_get_quote_uses_last_price_over_previous_close(tmp_path):
    fake_ticker = MagicMock()
    fake_ticker.fast_info = {
        "last_price": 110.0,
        "previous_close": 100.0,
        "last_time": 1_704_177_000,
    }
    fake_ticker.info = {}
    src = YFinanceSource(intraday_cache=FileCache(tmp_path, ttl_seconds=60))
    with patch("yfinance.Ticker", return_value=fake_ticker):
        quote = src.get_quote("AAPL.US")
    assert quote is not None
    assert quote["last_price"] == 110.0
    assert quote["previous_close"] == 100.0
    assert quote["change_pct"] == pytest.approx(0.1)
    assert quote["source"] == "yfinance_quote"


def test_get_info_extracts_relevant_fields(tmp_path):
    fake_ticker = MagicMock()
    fake_ticker.info = {
        "trailingPE": 28.5,
        "marketCap": 3_000_000_000_000,
        "fiftyTwoWeekHigh": 240.0,
        "fiftyTwoWeekLow": 160.0,
        "dividendYield": 0.37,            # yfinance percent: 0.37 means 0.37%
        "regularMarketVolume": 50_000_000,
        "regularMarketOpen": 220.0,
        "regularMarketDayHigh": 225.0,
        "regularMarketDayLow": 218.0,
        "regularMarketPreviousClose": 219.0,
        "shortName": "Apple Inc.",
    }
    src = YFinanceSource(cache=FileCache(tmp_path))
    with patch("yfinance.Ticker", return_value=fake_ticker):
        info = src.get_info("AAPL.US")
    assert info is not None
    assert info["pe_ratio"] == 28.5
    assert info["market_cap"] == 3_000_000_000_000
    assert info["week52_high"] == 240.0
    assert info["dividend_yield"] == 0.0037
    assert info["open"] == 220.0
    assert info["day_high"] == 225.0
    assert info["day_low"] == 218.0
    assert info["previous_close"] == 219.0
    assert info["name"] == "Apple Inc."
