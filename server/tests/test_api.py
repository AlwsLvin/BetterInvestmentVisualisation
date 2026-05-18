"""End-to-end FastAPI tests with a fake DataSource so the suite stays offline."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data.base import DataSource, DataSourceError
from app.api.portfolio import (
    _backtest_response,
    _range_end,
    _range_start,
    _rolling_execution_segments,
    _rolling_execution_start,
    _training_window_for_segment,
)
from app.deps import get_data_source
from app.main import app


class FakeDataSource(DataSource):
    name = "fake"

    def __init__(self):
        self.fail = False
        self.price_calls: list[tuple[str, date, date]] = []
        self.ohlc_calls: list[tuple[str, date, date]] = []
        self.intraday_calls: list[tuple[str, str, str]] = []
        self.intraday_failures: set[tuple[str, str, str]] = set()

    def _series(self, symbol: str, start: date, end: date) -> pd.Series:
        if symbol == "LISTED.US":
            start = max(start, date(2024, 1, 3))
        if symbol in {"NEW10.US", "NEW40.US"}:
            execution_end = _range_end(date.today(), "1y")
            execution_start = _range_start(execution_end, "1y")
            _train_start, train_end = _training_window_for_segment(execution_start, "1y")
            if symbol == "NEW10.US":
                listing_start = pd.bdate_range(
                    end=pd.Timestamp(train_end), periods=10,
                )[0].date()
            else:
                listing_start = pd.bdate_range(
                    end=pd.Timestamp(train_end), periods=40,
                )[0].date()
            start = max(start, listing_start)
        rng = pd.bdate_range(start, end)
        if len(rng) == 0:
            raise DataSourceError(f"no data for {symbol}")
        if symbol == "MVUP.US":
            return pd.Series(np.linspace(100.0, 200.0, len(rng)), index=rng, name=symbol)
        if symbol == "MVDOWN.US":
            return pd.Series([100.0] * len(rng), index=rng, name=symbol)
        rng_state = np.random.RandomState(abs(hash(symbol)) % (2**32))
        steps = rng_state.normal(0.0005, 0.012, len(rng))
        prices = 100 * np.exp(np.cumsum(steps))
        return pd.Series(prices, index=rng, name=symbol)

    def get_prices(self, symbol: str, start: date, end: date) -> pd.Series:
        if self.fail:
            raise DataSourceError(f"forced failure for {symbol}")
        self.price_calls.append((symbol, start, end))
        return self._series(symbol, start, end)

    def get_intraday_prices(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.Series:
        if self.fail:
            raise DataSourceError(f"forced failure for {symbol}")
        idx = pd.date_range(
            pd.Timestamp("2026-05-11 09:30"),
            periods=4,
            freq="5min",
        )[::-1]
        return pd.Series([103.0, 102.0, 101.0, 100.0], index=idx, name=symbol)

    def get_intraday_prices_tz(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.Series:
        self.intraday_calls.append((symbol, period, interval))
        if (symbol, period, interval) in self.intraday_failures:
            raise DataSourceError(f"forced intraday failure for {symbol}")
        if symbol == "FXQUOTE=X":
            if period == "1d":
                idx = pd.DatetimeIndex([
                    "2026-05-15 20:30",
                    "2026-05-15 20:45",
                    "2026-05-15 20:55",
                ], tz="UTC")
                values = [1.33310, 1.33260, 1.33239]
            else:
                idx = pd.DatetimeIndex([
                    "2026-05-13 13:25",
                    "2026-05-14 23:55",
                    "2026-05-15 20:55",
                ], tz="UTC")
                values = [1.33500, 1.33400, 1.33239]
            return pd.Series(values, index=idx, name=symbol)
        if symbol.endswith("=X"):
            base = {
                "USDCNH=X": 6.81442,
                "CNH=X": 6.81442,
                "USDHKD=X": 7.82930,
                "USDJPY=X": 158.73100,
                "EURUSD=X": 1.16306,
                "GBPUSD=X": 1.33255,
                "AUDUSD=X": 0.71531,
                "USDCAD=X": 1.37470,
                "USDCHF=X": 0.78600,
                "USDKRW=X": 1300.0,
            }.get(symbol, 7.0)
            if period == "1d":
                idx = pd.DatetimeIndex([
                    "2026-05-15 20:40",
                    "2026-05-15 20:45",
                    "2026-05-15 20:50",
                    "2026-05-15 20:55",
                ], tz="UTC")
                values = [base * 0.999, base * 0.9995, base * 0.9998, base]
            else:
                idx = pd.DatetimeIndex([
                    "2026-05-11 01:25",
                    "2026-05-13 13:25",
                    "2026-05-13 23:55",
                    "2026-05-14 23:55",
                    "2026-05-15 20:55",
                ], tz="UTC")
                values = [base * 0.996, base * 0.997, base * 0.998, base * 0.999, base]
            return pd.Series(values, index=idx, name=symbol)
        if symbol == "^IXIC":
            idx_0511 = pd.date_range(
                "2026-05-11 09:30",
                periods=4,
                freq="5min",
                tz="America/New_York",
            )
            idx_0513 = pd.date_range(
                "2026-05-13 15:45",
                periods=4,
                freq="5min",
                tz="America/New_York",
            )
            return pd.Series(
                [
                    26200.0, 26210.0, 26220.0, 26239.75,
                    26120.0, 26140.0, 26160.0, 26168.60,
                ],
                index=idx_0511.append(idx_0513),
                name=symbol,
            )
        if symbol == "000001.SS":
            idx = pd.date_range(
                "2026-05-11 14:50",
                periods=2,
                freq="5min",
                tz="Asia/Shanghai",
            )
            return pd.Series([101.0, 102.0], index=idx, name=symbol)
        if symbol == "^N225":
            idx = pd.date_range(
                "2026-05-11 09:00",
                periods=2,
                freq="5min",
                tz="Asia/Tokyo",
            )
            return pd.Series([62600.0, 62437.77], index=idx, name=symbol)
        if symbol == "000300.SS":
            idx = pd.date_range(
                pd.Timestamp(date.today()).replace(hour=1, minute=30, tzinfo=timezone.utc),
                periods=4,
                freq="5min",
            )[::-1]
            return pd.Series([103.0, 102.0, 101.0, 100.0], index=idx, name=symbol)
        if symbol == "YDAY.US":
            idx = pd.date_range(
                "2026-05-13 09:30",
                periods=4,
                freq="5min",
                tz="America/New_York",
            )
            return pd.Series([100.0, 101.0, 102.0, 103.0], index=idx, name=symbol)
        if symbol == "7203.T":
            idx = pd.date_range(
                "2026-05-14 09:00",
                periods=4,
                freq="5min",
                tz="Asia/Tokyo",
            )
            return pd.Series([100.0, 101.0, 102.0, 103.0], index=idx, name=symbol)
        if symbol == "000660.KS":
            idx = pd.date_range(
                "2026-05-14 09:00",
                periods=4,
                freq="5min",
                tz="Asia/Seoul",
            )
            return pd.Series([100.0, 101.0, 102.0, 103.0], index=idx, name=symbol)
        return self.get_intraday_prices(symbol, period=period, interval=interval)

    def get_intraday_ohlc_tz(
        self, symbol: str, period: str = "1d", interval: str = "5m"
    ) -> pd.DataFrame:
        self.intraday_calls.append((symbol, period, interval))
        if (symbol, period, interval) in self.intraday_failures:
            raise DataSourceError(f"forced intraday failure for {symbol}")
        if symbol == "USDHKD=X" and period in {"7d", "60d"}:
            idx = pd.DatetimeIndex([
                "2026-05-13 20:55",
                "2026-05-13 21:01",
                "2026-05-14 12:00",
                "2026-05-14 20:59",
                "2026-05-14 21:01",
            ], tz="UTC")
            frame = pd.DataFrame({
                "Open": [7.82880, 7.82990, 7.83010, 7.83120, 7.83280],
                "High": [7.82920, 7.83020, 7.83320, 7.83290, 7.83330],
                "Low": [7.82850, 7.82980, 7.82870, 7.83100, 7.83240],
                "Close": [7.82900, 7.82995, 7.83150, 7.83255, 7.83310],
                "Volume": [0] * 5,
            }, index=idx)
            if period == "7d":
                return frame.iloc[2:]
            return frame
        if symbol == "USDHKD=X" and period == "2y" and interval == "1h":
            idx = pd.DatetimeIndex([
                "2026-05-12 12:00",
                "2026-05-12 20:59",
            ], tz="UTC")
            return pd.DataFrame({
                "Open": [7.80000, 7.80400],
                "High": [7.80200, 7.80600],
                "Low": [7.79900, 7.80300],
                "Close": [7.80400, 7.80500],
                "Volume": [0] * 2,
            }, index=idx)
        if period == "2y" and interval == "1h":
            raise DataSourceError(f"no long intraday data for {symbol}")
        close = self.get_intraday_prices_tz(symbol, period=period, interval=interval)
        return pd.DataFrame({
            "Open": close - 1.0,
            "High": close + 1.0,
            "Low": close - 2.0,
            "Close": close,
            "Volume": [100_000] * len(close),
        }, index=close.index)

    def get_exchange(self, symbol: str):
        if symbol in {"AAPL.US", "NVDA.US", "MVUP.US"}:
            return "NMS"
        return "NYQ"

    def get_quote(self, symbol: str):
        if symbol == "FXQUOTE=X":
            return {
                "last_price": 1.33241,
                "previous_close": 1.34000,
                "change_pct": 1.33241 / 1.34000 - 1.0,
                "as_of": pd.Timestamp("2026-05-15T20:41:00Z").to_pydatetime(),
                "source": "fake_quote",
            }
        if symbol.endswith("=X"):
            base = {
                "USDCNH=X": 6.81442,
                "CNH=X": 6.81442,
                "USDHKD=X": 7.82930,
                "USDJPY=X": 158.73100,
                "EURUSD=X": 1.16306,
                "GBPUSD=X": 1.33255,
                "AUDUSD=X": 0.71531,
                "USDCAD=X": 1.37470,
                "USDCHF=X": 0.78600,
                "USDKRW=X": 1300.0,
            }.get(symbol, 7.0)
            return {
                "last_price": base * 1.1,
                "previous_close": base * 0.995,
                "change_pct": (base * 1.1) / (base * 0.995) - 1.0,
                "as_of": pd.Timestamp("2026-05-17T13:16:07Z").to_pydatetime(),
                "source": "fake_quote",
            }
        if symbol == "^IXIC":
            return {
                "last_price": 26247.08,
                "previous_close": 26000.0,
                "change_pct": 26247.08 / 26000.0 - 1.0,
                "as_of": pd.Timestamp("2026-05-11T13:45:00Z").to_pydatetime(),
                "source": "fake_quote",
            }
        if symbol == "^N225":
            return {
                "last_price": 62450.0,
                "previous_close": 62713.65,
                "change_pct": 62450.0 / 62713.65 - 1.0,
                "as_of": pd.Timestamp("2026-05-11T06:00:00Z").to_pydatetime(),
                "source": "fake_quote",
            }
        if symbol == "000660.KS":
            return {
                "last_price": 99.7,
                "previous_close": 100.0,
                "change_pct": -0.003,
                "as_of": pd.Timestamp("2026-05-14T02:05:00Z").to_pydatetime(),
                "source": "fake_quote",
            }
        if symbol == "STALE.US":
            return {
                "last_price": 120.0,
                "previous_close": 100.0,
                "change_pct": 0.2,
                "as_of": pd.Timestamp("2026-05-11T13:45:00Z").to_pydatetime(),
                "source": "fake_quote",
            }
        return {
            "last_price": 110.0,
            "previous_close": 100.0,
            "change_pct": 0.1,
            "as_of": pd.Timestamp("2026-05-11T06:55:00Z").to_pydatetime(),
            "source": "fake_quote",
        }

    def get_dividends(self, symbol: str, start: date, end: date):
        if symbol == "NODIV.US":
            return None
        idx = pd.date_range(start, end, freq="QS")
        if len(idx) == 0:
            return None
        return pd.Series([0.25] * len(idx), index=idx, name=symbol)

    def get_ohlc(self, symbol: str, start: date, end: date):
        if self.fail:
            raise DataSourceError(f"forced failure for {symbol}")
        self.ohlc_calls.append((symbol, start, end))
        if symbol == "USDCNH=X":
            day = date(2026, 5, 15)
            if not start <= day <= end:
                raise DataSourceError(f"no data for {symbol}")
            close = 6.81442
            return pd.DataFrame({
                "Open": [close],
                "High": [close * 1.001],
                "Low": [close * 0.999],
                "Close": [close],
                "Volume": [0],
            }, index=pd.DatetimeIndex([pd.Timestamp(day)]))
        if symbol == "CNH=X":
            rows = []
            idx = []
            for day, close in [
                (date(2026, 5, 13), 6.79000),
                (date(2026, 5, 14), 6.78608),
                (date(2026, 5, 15), 6.81442),
                (date(2026, 5, 17), 6.90000),
            ]:
                if start <= day <= end:
                    idx.append(pd.Timestamp(day))
                    rows.append(close)
            if not idx:
                raise DataSourceError(f"no data for {symbol}")
            return pd.DataFrame({
                "Open": rows,
                "High": [v * 1.001 for v in rows],
                "Low": [v * 0.999 for v in rows],
                "Close": rows,
                "Volume": [0] * len(rows),
            }, index=pd.DatetimeIndex(idx))
        if symbol == "^IXIC":
            rows = []
            idx = []
            if start <= date(2026, 5, 8) <= end:
                idx.append(pd.Timestamp("2026-05-08"))
                rows.append(26000.0)
            if start <= date(2026, 5, 11) <= end:
                idx.append(pd.Timestamp("2026-05-11"))
                rows.append(26247.08)
            if not idx:
                raise DataSourceError(f"no data for {symbol}")
            return pd.DataFrame({
                "Open": rows,
                "High": rows,
                "Low": rows,
                "Close": rows,
                "Volume": [100_000] * len(rows),
            }, index=pd.DatetimeIndex(idx))
        if symbol == "^N225":
            rows = []
            idx = []
            if start <= date(2026, 5, 8) <= end:
                idx.append(pd.Timestamp("2026-05-08"))
                rows.append(62713.65)
            if start <= date(2026, 5, 11) <= end:
                idx.append(pd.Timestamp("2026-05-11"))
                rows.append(62417.88)
            if not idx:
                raise DataSourceError(f"no data for {symbol}")
            return pd.DataFrame({
                "Open": rows,
                "High": rows,
                "Low": rows,
                "Close": rows,
                "Volume": [100_000] * len(rows),
            }, index=pd.DatetimeIndex(idx))
        if symbol == "000660.KS" and start <= date(2026, 5, 13) <= end <= date(2026, 5, 13):
            return pd.DataFrame({
                "Open": [100.0],
                "High": [101.0],
                "Low": [99.0],
                "Close": [100.0],
                "Volume": [100_000],
            }, index=pd.DatetimeIndex([pd.Timestamp("2026-05-13")]))
        if symbol == "STALE.US":
            prices = self._series(symbol, start, end)
            if pd.Timestamp("2026-05-12") in prices.index:
                prices.loc[pd.Timestamp("2026-05-12")] = 100.0
            if pd.Timestamp("2026-05-13") in prices.index:
                prices.loc[pd.Timestamp("2026-05-13")] = 105.0
            return pd.DataFrame({
                "Open": prices,
                "High": prices,
                "Low": prices,
                "Close": prices,
                "Volume": [100_000] * len(prices),
            })
        prices = self._series(symbol, start, end)
        return pd.DataFrame({
            "Open":  prices * 0.99,
            "High":  prices * 1.02,
            "Low":   prices * 0.98,
            "Close": prices,
            "Volume": [100_000] * len(prices),
        })

    def get_fresh_ohlc(self, symbol: str, start: date, end: date):
        if symbol == "^IXIC" and start <= date(2026, 5, 13) <= end:
            return pd.DataFrame({
                "Open": [26147.646484],
                "High": [26474.18],
                "Low": [25990.158203],
                "Close": [26402.34375],
                "Volume": [1_870_576_409],
            }, index=pd.DatetimeIndex([pd.Timestamp("2026-05-13")]))
        return self.get_ohlc(symbol, start, end)

    def get_raw_ohlc(self, symbol: str, start: date, end: date):
        if symbol == "RAW.US":
            idx = pd.bdate_range(start, end)
            return pd.DataFrame({
                "Open": [50.0] * len(idx),
                "High": [101.0] * len(idx),
                "Low": [49.0] * len(idx),
                "Close": [100.0] * len(idx),
                "Volume": [100_000] * len(idx),
            }, index=idx)
        return self.get_ohlc(symbol, start, end)

    def get_info(self, symbol: str):
        if symbol.startswith("NOINFO"):
            return None
        return {
            "pe_ratio": 25.0, "market_cap": 1_000_000_000,
            "week52_high": 200.0, "week52_low": 100.0,
            "dividend_yield": 0.02, "volume": 1_000_000,
            "open": 150.0, "day_high": 155.0, "day_low": 149.0,
            "previous_close": 148.0,
            "name": f"{symbol} Inc.",
        }


@pytest.fixture
def fake_source():
    src = FakeDataSource()
    app.dependency_overrides[get_data_source] = lambda: src
    yield src
    app.dependency_overrides.pop(get_data_source, None)


@pytest.fixture
def client(fake_source):
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_get_asset_returns_price_points_and_dividends(client):
    r = client.get("/api/asset/AAPL.US?range=1y")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "AAPL.US"
    assert body["range"] == "1y"
    assert len(body["points"]) > 200
    assert body["quote"] is not None
    assert body["quote"]["change_pct"] is not None
    first = body["points"][0]
    assert "date" in first and "close" in first
    assert body["dividends"] is not None
    assert all("date" in d and "amount" in d for d in body["dividends"])


def test_get_asset_no_dividends_returns_null(client):
    r = client.get("/api/asset/NODIV.US?range=30d")
    assert r.status_code == 200
    assert r.json()["dividends"] is None


def test_get_index_omits_dividends(client):
    r = client.get("/api/index/^GSPC?range=1y")
    assert r.status_code == 200
    body = r.json()
    assert body["dividends"] is None
    assert body["quote"] is not None
    assert body["quote"]["change_pct"] is not None


def test_get_index_intraday_returns_sorted_points(client):
    r = client.get("/api/intraday/index/^GSPC")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "^GSPC"
    assert data["period"] == "1d"
    assert data["interval"] == "5m"
    assert len(data["points"]) == 4
    times = [p["datetime"] for p in data["points"]]
    assert times == sorted(times)
    assert {"datetime", "close"} <= data["points"][0].keys()
    assert data["quote"]["previous_close"] is not None
    assert data["display_timezone"] == "America/New_York"


def test_get_asset_today_uses_intraday_points(client):
    r = client.get("/api/asset/AAPL.US?range=today&tz=Asia%2FShanghai")
    assert r.status_code == 200
    data = r.json()
    assert data["range"] == "today"
    assert len(data["points"]) == 4
    times = [p["date"] for p in data["points"]]
    assert times == sorted(times)
    assert "T" in times[0]
    assert data["market"] == "US"
    assert data["currency"] == "USD"
    assert data["market_status"] in ("open", "closed")
    assert data["ref_day"] is not None
    assert data["quote"]["last_price"] is not None


def test_get_asset_today_uses_one_minute_intraday(client, fake_source):
    r = client.get("/api/asset/AAPL.US?range=today&tz=Asia%2FShanghai")
    assert r.status_code == 200
    assert ("AAPL.US", "5d", "1m") in fake_source.intraday_calls


def test_get_asset_7d_intraday_prefers_one_minute(client, fake_source):
    r = client.get("/api/asset/AAPL.US?range=7d&intraday=true&ohlc=true")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["range"] == "7d"
    assert data["ohlc"] is not None
    assert "T" in data["points"][0]["date"]
    assert ("AAPL.US", "7d", "1m") in fake_source.intraday_calls


def test_get_asset_7d_intraday_falls_back_to_five_minute(client, fake_source):
    fake_source.intraday_failures.add(("AAPL.US", "7d", "1m"))
    r = client.get("/api/asset/AAPL.US?range=7d&intraday=true&ohlc=true")
    assert r.status_code == 200, r.text
    assert ("AAPL.US", "7d", "1m") in fake_source.intraday_calls
    assert ("AAPL.US", "7d", "5m") in fake_source.intraday_calls
    assert "T" in r.json()["points"][0]["date"]


def test_get_asset_7d_intraday_falls_back_to_daily(client, fake_source):
    fake_source.intraday_failures.add(("AAPL.US", "7d", "1m"))
    fake_source.intraday_failures.add(("AAPL.US", "7d", "5m"))
    r = client.get("/api/asset/AAPL.US?range=7d&intraday=true")
    assert r.status_code == 200, r.text
    assert "T" not in r.json()["points"][0]["date"]


def test_open_index_today_prefers_quote_over_intraday_last(client):
    from app.api import market as market_mod

    original_now = market_mod._now_utc
    market_mod._now_utc = lambda: datetime(2026, 5, 11, 13, 40, tzinfo=timezone.utc)
    try:
        r = client.get("/api/index/^IXIC?range=today&tz=Asia%2FShanghai")
        assert r.status_code == 200
        data = r.json()
        assert data["market_status"] == "open"
        assert data["quote"]["last_price"] == 26247.08
        assert data["quote"]["source"] == "quote_snapshot"
        assert data["points"][-1]["close"] == 26247.08
    finally:
        market_mod._now_utc = original_now


def test_closed_index_today_uses_fresh_daily_close_over_stale_daily_cache(client):
    from app.api import market as market_mod

    original_now = market_mod._now_utc
    market_mod._now_utc = lambda: datetime(2026, 5, 14, 2, 0, tzinfo=timezone.utc)
    try:
        r = client.get("/api/intraday/index/^IXIC?tz=Asia%2FShanghai")
        assert r.status_code == 200
        data = r.json()
        assert data["market_status"] == "closed"
        assert data["ref_day"] == "2026-05-13"
        assert data["quote"]["last_price"] == 26402.34375
        assert data["quote"]["source"] == "daily_close"
        assert data["points"][-1]["close"] == 26402.34375
    finally:
        market_mod._now_utc = original_now


def test_get_cn_index_today_displays_market_timezone(client):
    r = client.get("/api/index/000300.SS?range=today&tz=Asia%2FShanghai")
    assert r.status_code == 200
    data = r.json()
    assert data["display_timezone"] == "Asia/Shanghai"
    assert data["points"][0]["date"].endswith("09:30:00")


def test_closed_cn_index_today_labels_final_bar_at_market_close(client):
    from app.api import market as market_mod

    original_now = market_mod._now_utc
    market_mod._now_utc = lambda: datetime(2026, 5, 11, 7, 30, tzinfo=timezone.utc)
    try:
        r = client.get("/api/index/000001.SS?range=today&tz=Asia%2FShanghai")
        assert r.status_code == 200
        data = r.json()
        assert data["market_status"] == "closed"
        assert data["points"][-1]["date"].endswith("15:00:00")
        assert data["quote"]["as_of"].endswith("15:00:00")
    finally:
        market_mod._now_utc = original_now


def test_get_nikkei_today_uses_tokyo_timezone(client):
    from app.api import market as market_mod

    original_now = market_mod._now_utc
    market_mod._now_utc = lambda: datetime(2026, 5, 11, 7, 0, tzinfo=timezone.utc)
    try:
        r = client.get("/api/index/^N225?range=today&tz=Asia%2FShanghai")
        assert r.status_code == 200
        data = r.json()
        assert data["market"] == "JP"
        assert data["currency"] == "JPY"
        assert data["display_timezone"] == "Asia/Tokyo"
        assert data["quote"]["last_price"] == 62417.88
        assert data["quote"]["previous_close"] == 62713.65
        assert data["quote"]["change_pct"] == pytest.approx(-295.77 / 62713.65)
        assert data["quote"]["source"] == "daily_close"
        assert data["points"][-1]["close"] == 62417.88
    finally:
        market_mod._now_utc = original_now


def test_get_asset_accepts_ytd(client):
    r = client.get("/api/asset/AAPL.US?range=ytd")
    assert r.status_code == 200
    assert r.json()["range"] == "ytd"


def test_get_fx_intraday_returns_sorted_points(client):
    r = client.get("/api/intraday/fx/USDCNH%3DX?tz=Asia%2FShanghai")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "USDCNH=X"
    assert data["period"] == "1d"
    assert data["interval"] == "5m"
    assert data["display_timezone"] == "Asia/Shanghai"
    times = [p["datetime"] for p in data["points"]]
    assert times == sorted(times)
    assert {"datetime", "close"} <= data["points"][0].keys()
    assert not any(t.startswith("2026-05-17") for t in times)
    assert data["quote"]["source"] == "intraday_fallback"
    assert data["quote"]["last_price"] == pytest.approx(data["points"][-1]["close"])


def test_get_fx_intraday_uses_reasonable_quote_and_aligns_last_point(client):
    r = client.get("/api/intraday/fx/FXQUOTE%3DX?tz=Asia%2FShanghai")
    assert r.status_code == 200, r.text
    data = r.json()
    times = [p["datetime"] for p in data["points"]]
    assert times == sorted(times)
    assert data["quote"]["source"] == "quote_snapshot"
    assert data["quote"]["last_price"] == pytest.approx(1.33241)
    assert data["quote"]["as_of"].startswith("2026-05-15T20:41:00")
    assert data["points"][-1]["close"] == pytest.approx(1.33241)
    assert data["points"][-1]["datetime"].startswith("2026-05-16T04:41:00")
    assert all(t <= "2026-05-16T04:41:00" for t in times)


@pytest.mark.parametrize("symbol", [
    "USDCNH=X",
    "USDHKD=X",
    "USDJPY=X",
    "EURUSD=X",
    "GBPUSD=X",
    "AUDUSD=X",
    "USDCAD=X",
    "USDCHF=X",
])
def test_get_fx_intraday_rejects_future_quote_for_major_pairs(client, symbol):
    r = client.get(f"/api/intraday/fx/{symbol.replace('=', '%3D')}?tz=Asia%2FShanghai")
    assert r.status_code == 200, r.text
    data = r.json()
    times = [p["datetime"] for p in data["points"]]
    assert not any(t.startswith("2026-05-17") for t in times)
    assert data["quote"]["source"] == "intraday_fallback"
    assert data["quote"]["last_price"] == pytest.approx(data["points"][-1]["close"])


def test_get_fx_7d_intraday_prefers_one_minute(client, fake_source):
    r = client.get("/api/fx/USDCNH%3DX?range=7d&tz=Asia%2FShanghai")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["range"] == "7d"
    assert data["ohlc"] is not None
    assert "T" in data["points"][0]["date"]
    assert not any(p["date"].startswith("2026-05-17") for p in data["points"])
    assert data["quote"]["source"] == "intraday_fallback"
    assert ("USDCNH=X", "7d", "1m") in fake_source.intraday_calls


def test_get_fx_7d_intraday_falls_back_to_five_minute(client, fake_source):
    fake_source.intraday_failures.add(("USDCNH=X", "7d", "1m"))
    r = client.get("/api/fx/USDCNH%3DX?range=7d&tz=Asia%2FShanghai")
    assert r.status_code == 200, r.text
    assert ("USDCNH=X", "7d", "1m") in fake_source.intraday_calls
    assert ("USDCNH=X", "7d", "5m") in fake_source.intraday_calls


def test_get_fx_kline_omits_dividends_uses_safe_window_and_filters_weekends(client, fake_source):
    from app.api import market as market_mod

    original_now = market_mod._now_utc
    market_mod._now_utc = lambda: datetime(2026, 5, 17, 13, 16, tzinfo=timezone.utc)
    try:
        r = client.get("/api/fx-kline/USDCNH%3DX?period=day")
    finally:
        market_mod._now_utc = original_now
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["range"] == "dayK"
    assert data["dividends"] is None
    assert data["ohlc"] is not None
    assert "2026-05-17" not in {p["date"] for p in data["ohlc"]}
    assert data["quote"]["last_price"] == pytest.approx(6.81442)
    fx_calls = [call for call in fake_source.ohlc_calls if call[0] == "USDCNH=X"]
    fallback_calls = [call for call in fake_source.ohlc_calls if call[0] == "CNH=X"]
    assert fx_calls
    assert fallback_calls
    assert fx_calls[0][1] > date(1900, 1, 1)
    assert data["symbol"] == "USDCNH=X"
    assert len(data["ohlc"]) > 1


def test_get_fx_kline_uses_long_intraday_when_available(client, fake_source):
    r = client.get("/api/fx-kline/USDHKD%3DX?period=day&tz=Asia%2FShanghai")
    assert r.status_code == 200, r.text
    data = r.json()
    assert ("USDHKD=X", "2y", "1h") in fake_source.intraday_calls
    row = next(point for point in data["ohlc"] if point["label"] == "2026-05-12")
    assert row["open"] == pytest.approx(7.80000)
    assert row["high"] == pytest.approx(7.80600)
    assert row["low"] == pytest.approx(7.79900)
    assert row["close"] == pytest.approx(7.80500)
    notice_text = " · ".join(n["text"] for n in data["notices"])
    assert "1小时分时聚合" in notice_text
    assert "5分钟分时聚合" in notice_text


def test_get_fx_kline_returns_source_notice_when_long_intraday_missing(client, fake_source):
    r = client.get("/api/fx-kline/EURUSD%3DX?period=day&tz=Asia%2FShanghai")
    assert r.status_code == 200, r.text
    data = r.json()
    assert ("EURUSD=X", "2y", "1h") in fake_source.intraday_calls
    notices = data["notices"]
    assert notices
    assert any("Yahoo日线OHLC" in notice["text"] for notice in notices)


def test_get_fx_kline_uses_new_york_cutoff_for_daily_ohlc(client):
    r = client.get("/api/fx-kline/USDHKD%3DX?period=day&tz=Asia%2FShanghai")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["display_timezone"] == "Asia/Shanghai"
    row = next(point for point in data["ohlc"] if point["label"] == "2026-05-14")
    assert row["period_start"] == "2026-05-14"
    assert row["period_end"] == "2026-05-14"
    assert row["open"] == pytest.approx(7.82990)
    assert row["high"] == pytest.approx(7.83320)
    assert row["low"] == pytest.approx(7.82870)
    assert row["close"] == pytest.approx(7.83255)


def test_get_asset_invalid_range_400(client):
    r = client.get("/api/asset/AAPL.US?range=10y")
    assert r.status_code == 422


def test_v21_range_boundaries_are_one_year_and_ytd():
    today = date(2026, 5, 11)
    end = _range_end(today, "1y")
    assert end == date(2026, 5, 8)
    assert _range_start(end, "1y") == date(2025, 5, 9)
    assert _rolling_execution_start(end, "1y") == date(2025, 5, 9)
    assert _range_start(today, "ytd") == date(2026, 1, 1)
    assert _rolling_execution_start(today, "ytd") == date(2026, 1, 1)


def test_backtest_response_keeps_1y_annualized_return():
    bt = type("BT", (), {
        "annualized_return": 0.12,
        "cumulative_return": 0.10,
        "dates": [pd.Timestamp("2026-05-11")],
        "nav": [112.0],
        "cash_invested": [100.0],
        "return_pct": [0.12],
        "invest_dates": [pd.Timestamp("2026-05-11")],
        "max_drawdown": 0.0,
        "final_nav": 112.0,
        "total_invested": 100.0,
        "per_asset_final_value": {"AAPL.US": 112.0},
        "cash_left": {"USD": 0.0},
    })()
    assert _backtest_response(bt, range_key="1y").annualized_return == 0.12


def test_get_asset_with_ohlc_returns_ohlc_field(client):
    r = client.get("/api/asset/AAPL.US?range=30d&ohlc=true")
    assert r.status_code == 200
    body = r.json()
    assert body["ohlc"] is not None
    sample = body["ohlc"][0]
    assert {"date", "open", "high", "low", "close"} <= sample.keys()
    assert sample["high"] >= sample["close"] >= sample["low"]


def test_get_asset_today_with_ohlc_returns_intraday_ohlc(client):
    r = client.get("/api/asset/AAPL.US?range=today&ohlc=true")
    assert r.status_code == 200
    body = r.json()
    assert body["ohlc"] is not None
    assert "T" in body["ohlc"][0]["date"]
    assert body["ohlc"][0]["open"] != 0


def test_get_asset_kline_day_returns_daily_boxes(client):
    r = client.get("/api/asset-kline/LISTED.US?period=day")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["range"] == "dayK"
    assert body["ohlc"] is not None
    assert body["ohlc"][0]["period_start"] == body["ohlc"][0]["period_end"]
    assert body["ohlc"][0]["label"] == body["ohlc"][0]["date"]
    assert body["ohlc"][0]["high"] >= body["ohlc"][0]["open"] >= body["ohlc"][0]["low"]


def test_get_asset_kline_quarter_and_year_aggregate_calendar_periods(client):
    quarter = client.get("/api/asset-kline/LISTED.US?period=quarter")
    year = client.get("/api/asset-kline/LISTED.US?period=year")
    assert quarter.status_code == 200, quarter.text
    assert year.status_code == 200, year.text

    q_rows = quarter.json()["ohlc"]
    assert q_rows[0]["label"] == "2024 Q1"
    assert q_rows[0]["period_start"] == "2024-01-01"
    assert q_rows[0]["period_end"].startswith("2024-03-")
    assert q_rows[0]["high"] >= q_rows[0]["close"] >= q_rows[0]["low"]

    y_rows = year.json()["ohlc"]
    labels = [row["label"] for row in y_rows]
    assert "2024" in labels
    assert str(date.today().year) in labels
    current = y_rows[-1]
    assert current["period_start"] == f"{date.today().year}-01-01"
    assert current["period_end"] <= date.today().isoformat()
    assert current["high"] >= current["open"] >= current["low"]


def test_get_asset_without_ohlc_omits_ohlc(client):
    r = client.get("/api/asset/AAPL.US?range=30d")
    assert r.status_code == 200
    assert r.json()["ohlc"] is None


def test_get_asset_info_returns_fundamentals(client):
    r = client.get("/api/asset/AAPL.US/info")
    assert r.status_code == 200
    body = r.json()
    assert body["pe_ratio"] == 25.0
    assert body["week52_high"] == 200.0


def test_get_asset_info_missing_returns_empty_object(client):
    r = client.get("/api/asset/NOINFO.US/info")
    assert r.status_code == 200
    assert r.json() == {
        "name": None, "pe_ratio": None, "market_cap": None,
        "week52_high": None, "week52_low": None, "dividend_yield": None,
        "volume": None, "open": None, "day_high": None, "day_low": None,
        "previous_close": None,
    }


def test_allocate_portfolio_returns_weights_summing_to_one(client):
    body = {
        "tickers": ["AAPL.US", "NVDA.US", "BIL.US", "KO.US"],
        "style": "high_return",
        "scheme": "softmax",
        "tau": 0.5,
        "lookback_days": 365,
    }
    r = client.post("/api/portfolio/allocate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data["allocation"].keys()) == set(body["tickers"])
    assert abs(sum(data["allocation"].values()) - 1.0) < 1e-6
    assert abs(sum(data["global_weights"].values()) - 1.0) < 1e-6
    assert all(0 <= v <= 1 for v in data["allocation"].values())
    assert "metrics" in data


def test_allocate_low_volatility_style_favors_bil(client):
    body = {
        "tickers": ["NVDA.US", "BIL.US"],
        "style": "low_volatility",
        "scheme": "softmax",
        "tau": 0.1,
        "lookback_days": 365,
    }
    r = client.post("/api/portfolio/allocate", json=body)
    assert r.status_code == 200
    alloc = r.json()["allocation"]
    assert alloc["BIL.US"] != alloc["NVDA.US"]


def test_backtest_returns_curve_and_invest_dates(client):
    body = {
        "weights": {"AAPL.US": 0.5, "BIL.US": 0.5},
        "plan": {"amount": 1000, "frequency": "monthly:1"},
        "range": "1y",
    }
    r = client.post("/api/backtest", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["points"]) > 200
    sample = data["points"][50]
    assert {"date", "nav", "cash_invested", "return_pct"} <= sample.keys()
    assert 8 <= len(data["invest_dates"]) <= 14
    assert "cumulative_return" in data
    assert "annualized_return" in data
    assert data["annualized_return"] is not None
    assert "max_drawdown" in data
    assert abs(
        sum(data["per_asset_final_value"].values())
        + data["cash_left"]["USD"]
        - data["final_nav"]
    ) < 1e-3


def test_backtest_today_returns_intraday_curve_without_annualized(client):
    body = {
        "weights": {"AAPL.US": 1.0},
        "plan": {"amount": 1000, "frequency": "daily"},
        "range": "today",
    }
    r = client.post("/api/backtest", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["points"]) == 4
    assert data["annualized_return"] is None
    assert "T" in data["points"][0]["date"]
    assert data["per_asset_status"]["AAPL.US"]["market"] == "US"
    assert data["per_asset_status"]["AAPL.US"]["currency"] == "USD"
    assert data["purchase_events"][0]["price"] == 99.0


def test_backtest_3y_returns_chronological_points(client):
    body = {
        "weights": {"AAPL.US": 0.5, "BIL.US": 0.5},
        "plan": {"amount": 1000, "frequency": "monthly:1"},
        "range": "3y",
    }
    r = client.post("/api/backtest", json=body)
    assert r.status_code == 200, r.text
    points = r.json()["points"]
    dates = [p["date"] for p in points]
    assert dates == sorted(dates)
    assert dates[0] < dates[-1]
    assert len(points) > 700


def test_rolling_allocation_backtest_returns_training_schedule(client):
    body = {
        "tickers": ["AAPL.US", "BIL.US"],
        "style": "high_return",
        "scheme": "softmax",
        "tau": 0.5,
        "plan": {"amount": 1000, "frequency": "monthly:1"},
        "range": "1y",
    }
    r = client.post("/api/backtest/rolling-allocation", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["points"]) > 200
    assert data["benchmark"] is not None
    assert data["benchmark_components"]
    assert data["benchmark_points"]
    assert data["benchmark_points"][0]["return_pct"] == pytest.approx(0.0)
    assert data["timings"]["total_ms"] >= 0
    assert data["timings"]["training_data_fetch_ms"] >= 0
    assert len(data["allocation_schedule"]) == 1
    expected_end = _range_end(date.today(), "1y")
    expected_start = _range_start(expected_end, "1y")
    expected_train_start, expected_train_end = _training_window_for_segment(expected_start, "1y")
    for row in data["allocation_schedule"]:
        assert row["effective_start"] == expected_start.isoformat()
        assert row["effective_end"] == expected_end.isoformat()
        assert row["training_start"] == expected_train_start.isoformat()
        assert row["training_end"] == expected_train_end.isoformat()
        assert set(row["allocation"]) == set(body["tickers"])
        assert abs(sum(row["allocation"].values()) - 1.0) < 1e-6
        assert row["metrics"]
        assert row["global_weights"]
        assert row["closeness"]
        assert row["indicators"]


def test_rolling_allocation_today_handles_previous_us_session_in_user_timezone(client):
    from app.api import portfolio as portfolio_mod

    original_now = portfolio_mod._now_utc
    portfolio_mod._now_utc = lambda: datetime(2026, 5, 14, 2, 0, tzinfo=timezone.utc)
    try:
        body = {
            "tickers": ["YDAY.US"],
            "plan": {"amount": 1000, "frequency": "daily"},
            "range": "today",
            "tz": "Asia/Shanghai",
        }
        r = client.post("/api/backtest/rolling-allocation", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["points"]) == 4
        assert data["annualized_return"] is None
        assert data["points"][0]["date"].startswith("2026-05-13T")
        assert data["per_asset_status"]["YDAY.US"]["ref_day"] == "2026-05-13"
        assert data["per_asset_status"]["YDAY.US"]["timezone"] == "America/New_York"
        assert data["allocation_schedule"]
        assert data["purchase_events"]
        window = data["execution_windows"]["YDAY.US"]
        assert window["market_timezone"] == "America/New_York"
        assert window["display_timezone"] == "Asia/Shanghai"
        assert window["ref_day"] == "2026-05-13"
        assert window["execution_start"].startswith("2026-05-13T")
        assert window["training_start"] == data["allocation_schedule"][-1]["training_start"]
        assert window["training_end"] == data["allocation_schedule"][-1]["training_end"]
    finally:
        portfolio_mod._now_utc = original_now


def test_rolling_allocation_today_reports_multi_market_execution_windows(client):
    from app.api import portfolio as portfolio_mod

    original_now = portfolio_mod._now_utc
    portfolio_mod._now_utc = lambda: datetime(2026, 5, 14, 2, 0, tzinfo=timezone.utc)
    try:
        body = {
            "tickers": ["YDAY.US", "7203.T", "000660.KS"],
            "plan": {"amount": 10_000, "frequency": "daily"},
            "range": "today",
            "tz": "Asia/Shanghai",
        }
        r = client.post("/api/backtest/rolling-allocation", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        windows = data["execution_windows"]
        assert windows["YDAY.US"]["market_timezone"] == "America/New_York"
        assert windows["7203.T"]["market_timezone"] == "Asia/Tokyo"
        assert windows["000660.KS"]["market_timezone"] == "Asia/Seoul"
        assert all(w["display_timezone"] == "Asia/Shanghai" for w in windows.values())
        assert all(w["execution_start"] and w["execution_end"] for w in windows.values())
        assert data["benchmark_points"]
        assert len(data["benchmark_points"]) == len(data["points"])
        assert data["benchmark_points"][0]["date"] == data["points"][0]["date"]
        assert data["benchmark_points"][0]["return_pct"] == pytest.approx(0.0)
        assert [p["date"] for p in data["benchmark_points"]] == [
            p["date"] for p in data["points"]
        ]
    finally:
        portfolio_mod._now_utc = original_now


def test_rolling_allocation_3y_uses_three_anchored_execution_windows(client):
    body = {
        "tickers": ["AAPL.US", "BIL.US"],
        "plan": {"amount": 1000, "frequency": "monthly:1"},
        "range": "3y",
    }
    r = client.post("/api/backtest/rolling-allocation", json=body)
    assert r.status_code == 200, r.text
    rows = r.json()["allocation_schedule"]
    expected_end = _range_end(date.today(), "3y")
    expected_start = _rolling_execution_start(expected_end, "3y")
    expected_segments = _rolling_execution_segments(expected_start, expected_end, "3y")
    assert len(rows) == 3
    assert [
        (row["effective_start"], row["effective_end"])
        for row in rows
    ] == [(s.isoformat(), e.isoformat()) for s, e in expected_segments]
    for row, (segment_start, _segment_end) in zip(rows, expected_segments):
        train_start, train_end = _training_window_for_segment(segment_start, "3y")
        assert row["training_start"] == train_start.isoformat()
        assert row["training_end"] == train_end.isoformat()


def test_rolling_allocation_30_day_window_rolls_1y_execution_in_30_day_segments(client):
    client.put(
        "/api/settings",
        json={
            "data_source": "yfinance",
            "benchmark": "^GSPC",
            "allocation_lookback_days": 30,
        },
    )
    try:
        body = {
            "tickers": ["AAPL.US", "BIL.US"],
            "plan": {"amount": 1000, "frequency": "monthly:1"},
            "range": "1y",
        }
        r = client.post("/api/backtest/rolling-allocation", json=body)
        assert r.status_code == 200, r.text
        rows = r.json()["allocation_schedule"]
        expected_end = _range_end(date.today(), "1y")
        expected_start = _rolling_execution_start(expected_end, "1y")
        expected_segments = _rolling_execution_segments(expected_start, expected_end, "1y", 30)

        assert len(rows) == len(expected_segments)
        assert len(rows) > 1
        assert [
            (row["effective_start"], row["effective_end"])
            for row in rows
        ] == [(s.isoformat(), e.isoformat()) for s, e in expected_segments]

        latest = rows[-1]
        latest_start, latest_end = expected_segments[-1]
        assert latest_end == expected_end
        assert latest_start == expected_end - timedelta(days=29)
        assert latest["training_start"] == (latest_start - timedelta(days=30)).isoformat()
        assert latest["training_end"] == (latest_start - timedelta(days=1)).isoformat()
    finally:
        client.put(
            "/api/settings",
            json={
                "data_source": "yfinance",
                "benchmark": "^GSPC",
                "allocation_lookback_days": 365,
            },
        )


def test_rolling_allocation_30d_uses_default_one_year_training_window(client):
    body = {
        "tickers": ["AAPL.US", "BIL.US"],
        "plan": {"amount": 1000, "frequency": "monthly:1"},
        "range": "30d",
    }
    r = client.post("/api/backtest/rolling-allocation", json=body)
    assert r.status_code == 200, r.text
    row = r.json()["allocation_schedule"][-1]
    effective_start = date.fromisoformat(row["effective_start"])
    train_start = date.fromisoformat(row["training_start"])
    train_end = date.fromisoformat(row["training_end"])
    assert train_end == effective_start - timedelta(days=1)
    assert 364 <= (train_end - train_start).days <= 366


def test_rolling_allocation_uses_configured_training_window_for_all_ranges(client):
    client.put(
        "/api/settings",
        json={
            "data_source": "yfinance",
            "benchmark": "^GSPC",
            "allocation_lookback_days": 90,
        },
    )
    try:
        for range_key in ("today", "1y", "3y"):
            body = {
                "tickers": ["YDAY.US" if range_key == "today" else "AAPL.US", "BIL.US"],
                "plan": {"amount": 10_000, "frequency": "monthly:1"},
                "range": range_key,
                "tz": "Asia/Shanghai",
            }
            r = client.post("/api/backtest/rolling-allocation", json=body)
            assert r.status_code == 200, r.text
            for row in r.json()["allocation_schedule"]:
                effective_start = date.fromisoformat(row["effective_start"])
                assert row["training_start"] == (effective_start - timedelta(days=90)).isoformat()
                assert row["training_end"] == (effective_start - timedelta(days=1)).isoformat()
    finally:
        client.put(
            "/api/settings",
            json={
                "data_source": "yfinance",
                "benchmark": "^GSPC",
                "allocation_lookback_days": 365,
            },
        )


def test_rolling_allocation_30_day_window_keeps_enough_training_samples(client):
    client.put(
        "/api/settings",
        json={
            "data_source": "yfinance",
            "benchmark": "^GSPC",
            "allocation_lookback_days": 30,
        },
    )
    try:
        body = {
            "tickers": ["AAPL.US", "BIL.US"],
            "plan": {"amount": 1000, "frequency": "monthly:1"},
            "range": "30d",
        }
        r = client.post("/api/backtest/rolling-allocation", json=body)
        assert r.status_code == 200, r.text
        row = r.json()["allocation_schedule"][-1]
        assert set(row["allocation"]) == {"AAPL.US", "BIL.US"}
    finally:
        client.put(
            "/api/settings",
            json={
                "data_source": "yfinance",
                "benchmark": "^GSPC",
                "allocation_lookback_days": 365,
            },
        )


def test_rolling_allocation_excludes_less_than_30_day_training_history(client):
    body = {
        "tickers": ["AAPL.US", "NEW10.US"],
        "plan": {"amount": 1000, "frequency": "monthly:1"},
        "range": "1y",
    }
    r = client.post("/api/backtest/rolling-allocation", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    excluded = [
        w for w in data["data_warnings"]
        if w["ticker"] == "NEW10.US" and w["action"] == "excluded"
    ]
    assert excluded
    assert all("NEW10.US" not in row["allocation"] for row in data["allocation_schedule"])


def test_rolling_allocation_warns_partial_history_and_keeps_ticker(client):
    body = {
        "tickers": ["AAPL.US", "NEW40.US"],
        "plan": {"amount": 1000, "frequency": "monthly:1"},
        "range": "1y",
    }
    r = client.post("/api/backtest/rolling-allocation", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    partial = [
        w for w in data["data_warnings"]
        if w["ticker"] == "NEW40.US" and w["action"] == "annualized_short_history"
    ]
    assert partial
    current_year = date.today().year
    current_schedule = next(row for row in data["allocation_schedule"] if row["year"] == current_year)
    assert "NEW40.US" in current_schedule["allocation"]


def test_rolling_backtest_returns_purchase_events(client):
    body = {
        "tickers": ["AAPL.US", "BIL.US"],
        "plan": {"amount": 10_000, "frequency": "monthly:1"},
        "range": "1y",
    }
    r = client.post("/api/backtest/rolling-allocation", json=body)
    assert r.status_code == 200, r.text
    events = r.json()["purchase_events"]
    assert events
    sample = events[0]
    assert {
        "ticker", "purchased_at", "timezone", "price", "fx_rate",
        "price_usd", "shares", "total_shares",
    } <= sample.keys()
    assert sample["shares"] > 0
    assert sample["total_shares"] >= sample["shares"]


def test_backtest_execution_uses_raw_open_price(client):
    body = {
        "weights": {"RAW.US": 1.0},
        "plan": {"amount": 10_000, "frequency": "every:5000d"},
        "range": "7d",
    }
    r = client.post("/api/backtest", json=body)
    assert r.status_code == 200, r.text
    events = r.json()["purchase_events"]
    assert events
    assert events[0]["price"] == 50.0


def test_backtest_weights_must_sum_to_one(client):
    body = {
        "weights": {"AAPL.US": 0.3, "BIL.US": 0.3},
        "plan": {"amount": 1000, "frequency": "monthly:1"},
        "range": "1y",
    }
    r = client.post("/api/backtest", json=body)
    assert r.status_code == 400


def test_evaluate_portfolio_returns_classic_metrics(client):
    body = {
        "weights": {"AAPL.US": 0.5, "BIL.US": 0.5},
        "range": "1y",
    }
    r = client.post("/api/portfolio/evaluate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "portfolio" in data
    p = data["portfolio"]
    for key in ("cumulative_return", "annualized_return", "volatility",
                "max_drawdown", "beta", "alpha", "sharpe"):
        assert key in p
    assert len(data["holdings"]) == 2
    assert {h["ticker"] for h in data["holdings"]} == {"AAPL.US", "BIL.US"}
    for h in data["holdings"]:
        assert h["last_price"] is not None
        assert "metrics" in h
    assert data["rf_source"] in ("bil_default", "constant_fallback", "override")


def test_evaluate_portfolio_with_rf_override(client):
    body = {
        "weights": {"AAPL.US": 1.0},
        "range": "1y",
        "rf_override": 0.05,
    }
    r = client.post("/api/portfolio/evaluate", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["rf_source"] == "override"
    assert abs(data["rf_used"] - 0.05) < 1e-9


def test_evaluate_portfolio_today_does_not_overflow(client):
    from app.api import portfolio as portfolio_mod

    original_now = portfolio_mod._now_utc
    portfolio_mod._now_utc = lambda: datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc)
    try:
        body = {
            "weights": {"AAPL.US": 1.0},
            "range": "today",
            "rf_override": 0.05,
            "tz": "Asia/Shanghai",
        }
        r = client.post("/api/portfolio/evaluate", json=body)
        assert r.status_code == 200, r.text
        portfolio = r.json()["portfolio"]
        assert np.isfinite(portfolio["annualized_return"])
        assert np.isfinite(portfolio["alpha"])
    finally:
        portfolio_mod._now_utc = original_now


def test_evaluate_korean_stock_reports_krw_currency(client):
    body = {
        "weights": {"000660.KS": 1.0},
        "range": "1y",
        "rf_override": 0.05,
    }
    r = client.post("/api/portfolio/evaluate", json=body)
    assert r.status_code == 200, r.text
    holding = r.json()["holdings"][0]
    assert holding["ticker"] == "000660.KS"
    assert holding["currency"] == "KRW"
    assert holding["last_price_usd"] is not None


def test_evaluate_non_today_daily_change_uses_quote_snapshot(client):
    from app.api import portfolio as portfolio_mod

    original_now = portfolio_mod._now_utc
    portfolio_mod._now_utc = lambda: datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc)
    try:
        body = {
            "weights": {"AAPL.US": 1.0},
            "range": "1y",
            "rf_override": 0.05,
        }
        r = client.post("/api/portfolio/evaluate", json=body)
        assert r.status_code == 200, r.text
        holding = r.json()["holdings"][0]
        assert holding["ticker"] == "AAPL.US"
        assert holding["daily_change"] == pytest.approx(0.1)
    finally:
        portfolio_mod._now_utc = original_now


def test_evaluate_non_today_daily_change_ignores_stale_quote(client):
    from app.api import portfolio as portfolio_mod

    original_now = portfolio_mod._now_utc
    portfolio_mod._now_utc = lambda: datetime(2026, 5, 14, 2, 0, tzinfo=timezone.utc)
    try:
        body = {
            "weights": {"STALE.US": 1.0},
            "range": "1y",
            "rf_override": 0.05,
        }
        r = client.post("/api/portfolio/evaluate", json=body)
        assert r.status_code == 200, r.text
        holding = r.json()["holdings"][0]
        assert holding["ticker"] == "STALE.US"
        assert holding["daily_change"] == pytest.approx(0.05)
    finally:
        portfolio_mod._now_utc = original_now


def test_evaluate_today_daily_change_uses_quote_previous_close_for_korean_stock(client):
    from app.api import portfolio as portfolio_mod

    original_now = portfolio_mod._now_utc
    portfolio_mod._now_utc = lambda: datetime(2026, 5, 14, 2, 0, tzinfo=timezone.utc)
    try:
        body = {
            "weights": {"000660.KS": 1.0},
            "range": "today",
            "rf_override": 0.05,
            "tz": "Asia/Shanghai",
        }
        r = client.post("/api/portfolio/evaluate", json=body)
        assert r.status_code == 200, r.text
        holding = r.json()["holdings"][0]
        assert holding["ticker"] == "000660.KS"
        assert holding["last_price"] == pytest.approx(99.7)
        assert holding["daily_change"] == pytest.approx(-0.003)
    finally:
        portfolio_mod._now_utc = original_now


def test_evaluate_hk_stock_uses_hk_beta_benchmark(client):
    body = {
        "weights": {"1398.HK": 1.0},
        "range": "1y",
        "rf_override": 0.05,
    }
    r = client.post("/api/portfolio/evaluate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["benchmark"] == "^HSI"
    holding = data["holdings"][0]
    assert holding["metrics"]["beta_benchmark"] == "^HSI"


def test_evaluate_nasdaq_stock_uses_nasdaq_beta_benchmark(client):
    body = {
        "weights": {"AAPL.US": 1.0},
        "range": "1y",
        "rf_override": 0.05,
    }
    r = client.post("/api/portfolio/evaluate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["benchmark"] == "^IXIC"
    assert data["benchmark_components"] == {"^IXIC": 1.0}
    assert data["holdings"][0]["metrics"]["beta_benchmark"] == "^IXIC"


def test_evaluate_non_nasdaq_us_stock_uses_sp500_benchmark(client):
    body = {
        "weights": {"KO.US": 1.0},
        "range": "1y",
        "rf_override": 0.05,
    }
    r = client.post("/api/portfolio/evaluate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["benchmark"] == "^GSPC"
    assert data["benchmark_components"] == {"^GSPC": 1.0}
    assert data["holdings"][0]["metrics"]["beta_benchmark"] == "^GSPC"


def test_evaluate_mixed_market_portfolio_reports_composite_benchmark(client):
    body = {
        "weights": {"AAPL.US": 0.60, "KO.US": 0.25, "1398.HK": 0.15},
        "range": "1y",
        "rf_override": 0.05,
    }
    r = client.post("/api/portfolio/evaluate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["benchmark"].startswith("Composite")
    assert "^IXIC" in data["benchmark"]
    assert "^GSPC" in data["benchmark"]
    assert "^HSI" in data["benchmark"]
    assert set(data["benchmark_components"]) == {"^IXIC", "^GSPC", "^HSI"}
    assert sum(data["benchmark_components"].values()) == pytest.approx(1.0)
    assert data["portfolio"]["beta"] is not None
    assert data["portfolio"]["alpha"] is not None


def test_evaluate_composite_benchmark_uses_latest_usd_market_value_weights(client):
    body = {
        "weights": {"MVUP.US": 0.5, "MVDOWN.US": 0.5},
        "range": "1y",
        "rf_override": 0.05,
    }
    r = client.post("/api/portfolio/evaluate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["benchmark_components"] == {
        "^IXIC": pytest.approx(2 / 3),
        "^GSPC": pytest.approx(1 / 3),
    }


def test_evaluate_default_rf_uses_365_days_before_eval_start(client, fake_source):
    body = {
        "weights": {"AAPL.US": 1.0},
        "range": "7d",
    }
    r = client.post("/api/portfolio/evaluate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    end = date.today()
    eval_start = end - timedelta(days=7)
    assert data["rf_source"] == "bil_default"
    assert data["rf_window_start"] == (eval_start - timedelta(days=365)).isoformat()
    assert data["rf_window_end"] == eval_start.isoformat()
    assert ("BIL.US", eval_start - timedelta(days=365), eval_start) in fake_source.price_calls


def test_evaluate_today_mixed_market_keeps_card_alive_with_null_beta_alpha(client):
    from app.api import portfolio as portfolio_mod

    original_now = portfolio_mod._now_utc
    portfolio_mod._now_utc = lambda: datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc)
    try:
        body = {
            "weights": {"AAPL.US": 0.5, "1398.HK": 0.5},
            "range": "today",
            "rf_override": 0.05,
            "tz": "Asia/Shanghai",
        }
        r = client.post("/api/portfolio/evaluate", json=body)
        assert r.status_code == 200, r.text
        portfolio = r.json()["portfolio"]
        assert portfolio["beta"] is None
        assert portfolio["alpha"] is None
    finally:
        portfolio_mod._now_utc = original_now


def test_evaluate_portfolio_weights_must_sum_to_one(client):
    r = client.post("/api/portfolio/evaluate",
                    json={"weights": {"AAPL.US": 0.3, "BIL.US": 0.3}, "range": "1y"})
    assert r.status_code == 400


def test_settings_round_trip(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json() == {
        "data_source": "yfinance",
        "benchmark": "^GSPC",
        "allocation_lookback_days": 365,
    }

    r = client.put(
        "/api/settings",
        json={
            "data_source": "yfinance",
            "benchmark": "QQQ",
            "allocation_lookback_days": 90,
        },
    )
    assert r.status_code == 200
    assert r.json()["benchmark"] == "QQQ"
    assert r.json()["allocation_lookback_days"] == 90

    r = client.get("/api/settings")
    assert r.json()["benchmark"] == "QQQ"
    assert r.json()["allocation_lookback_days"] == 90
    client.put(
        "/api/settings",
        json={
            "data_source": "yfinance",
            "benchmark": "^GSPC",
            "allocation_lookback_days": 365,
        },
    )


def test_settings_rejects_invalid_allocation_lookback(client):
    r = client.put(
        "/api/settings",
        json={
            "data_source": "yfinance",
            "benchmark": "^GSPC",
            "allocation_lookback_days": 45,
        },
    )
    assert r.status_code == 422


def test_data_source_failure_propagates_404(client, fake_source):
    fake_source.fail = True
    r = client.get("/api/asset/AAPL.US?range=1y")
    assert r.status_code == 404


def test_openapi_schema_available(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for p in (
        "/api/health",
        "/api/asset/{symbol}",
        "/api/asset/{symbol}/info",
        "/api/index/{code}",
        "/api/intraday/index/{code}",
        "/api/intraday/asset/{symbol}",
        "/api/intraday/fx/{symbol}",
        "/api/fx/{symbol}",
        "/api/fx-kline/{symbol}",
        "/api/portfolio/allocate",
        "/api/portfolio/evaluate",
        "/api/backtest",
        "/api/backtest/rolling-allocation",
        "/api/search",
        "/api/settings",
    ):
        assert p in paths


def test_search_returns_mocked_results(client):
    fake = [
        {"symbol": "AAPL", "longname": "Apple Inc.", "exchDisp": "NASDAQ",
         "typeDisp": "Equity", "isYahooFinance": True},
        {"symbol": "AAPL.MX", "shortname": "Apple Inc.", "exchDisp": "Mexico",
         "typeDisp": "Equity", "isYahooFinance": True},
        {"symbol": "BAD", "isYahooFinance": False},  # filtered
    ]
    from app.api import search as search_mod
    original = search_mod._yfinance_search
    search_mod._yfinance_search = lambda q, limit: [
        search_mod.SearchResult(
            symbol=item["symbol"],
            name=item.get("longname") or item.get("shortname", ""),
            exchange=item.get("exchDisp", ""),
            type=item.get("typeDisp", ""),
        )
        for item in fake if item.get("isYahooFinance", True)
    ]
    try:
        r = client.get("/api/search?q=apple")
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "apple"
        symbols = [r["symbol"] for r in data["results"]]
        assert "AAPL" in symbols and "BAD" not in symbols
    finally:
        search_mod._yfinance_search = original


def test_search_rejects_empty_query(client):
    r = client.get("/api/search?q=")
    assert r.status_code == 422


def test_search_clamps_limit(client):
    r = client.get("/api/search?q=apple&limit=100")
    assert r.status_code == 422
