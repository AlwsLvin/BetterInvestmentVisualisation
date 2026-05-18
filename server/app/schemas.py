from __future__ import annotations

from datetime import date as Date, datetime as DateTime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Style = Literal["high_return", "low_volatility", "balanced"]
Scheme = Literal["linear", "softmax", "power"]
Range = Literal["today", "7d", "30d", "90d", "ytd", "1y", "3y", "5y"]
MarketStatus = Literal["open", "closed"]
AllocationLookbackDays = Literal[30, 90, 180, 365]
KlinePeriod = Literal["day", "quarter", "year"]
NoticeKind = Literal["fx_kline_source_change"]


RANGE_DAYS: dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "1y": 365,
    "3y": 365 * 3,
    "5y": 365 * 5,
}


class PricePoint(BaseModel):
    date: Date | DateTime
    close: float
    open: float | None = None


class IntradayPoint(BaseModel):
    datetime: DateTime
    close: float


class DividendPoint(BaseModel):
    date: Date
    amount: float


class OHLCPoint(BaseModel):
    date: DateTime | Date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    period_start: Date | None = None
    period_end: Date | None = None
    label: str | None = None


class QuoteSnapshot(BaseModel):
    last_price: float | None = None
    previous_close: float | None = None
    change_pct: float | None = None
    as_of: DateTime | None = None
    source: str = "unknown"


class SeriesNotice(BaseModel):
    kind: NoticeKind
    date: Date
    text: str


class AssetInfo(BaseModel):
    name: str | None = None
    pe_ratio: float | None = None
    market_cap: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    dividend_yield: float | None = None
    volume: float | None = None
    open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    previous_close: float | None = None


class AssetSeries(BaseModel):
    symbol: str
    range: str
    points: list[PricePoint]
    ohlc: list[OHLCPoint] | None = None
    dividends: list[DividendPoint] | None = None
    market_status: MarketStatus | None = None
    ref_day: Date | None = None
    market: str | None = None
    currency: str | None = None
    display_timezone: str | None = None
    quote: QuoteSnapshot | None = None
    notices: list[SeriesNotice] | None = None


class IntradaySeries(BaseModel):
    symbol: str
    period: str
    interval: str
    points: list[IntradayPoint]
    market_status: MarketStatus | None = None
    ref_day: Date | None = None
    market: str | None = None
    currency: str | None = None
    display_timezone: str | None = None
    quote: QuoteSnapshot | None = None


class AssetMarketStatus(BaseModel):
    market: str
    ref_day: Date
    status: MarketStatus
    currency: str
    timezone: str


class AssetMetricsOut(BaseModel):
    annualized_roi: float
    max_drawdown: float
    drawdown_duration: float
    recovery_time: float
    volatility: float
    beta: float
    beta_benchmark: str | None = None
    dividend_yield: float | None


class AllocateRequest(BaseModel):
    tickers: list[str] = Field(min_length=1)
    style: Style = "high_return"
    scheme: Scheme = "softmax"
    tau: float = 1.0
    power: float = 2.0
    floor: float = 0.0
    lookback_days: int = 365 * 3
    spread_pct: float = 0.1


class AllocateResponse(BaseModel):
    tickers: list[str]
    indicators: list[str]
    style: Style
    scheme: Scheme
    has_dividend: bool
    global_weights: dict[str, float]
    metrics: dict[str, AssetMetricsOut]
    closeness: dict[str, float]
    allocation: dict[str, float]
    constant_criteria: list[str]


class PlanIn(BaseModel):
    amount: float = Field(gt=0)
    frequency: str = "monthly:1"


class BacktestRequest(BaseModel):
    weights: dict[str, float] = Field(min_length=1)
    plan: PlanIn
    range: Range = "1y"
    tz: str | None = None


class RollingBacktestRequest(BaseModel):
    tickers: list[str] = Field(min_length=1)
    style: Style = "high_return"
    scheme: Scheme = "softmax"
    tau: float = 1.0
    power: float = 2.0
    floor: float = 0.0
    spread_pct: float = 0.1
    plan: PlanIn
    range: Range = "1y"
    tz: str | None = None


class BacktestPoint(BaseModel):
    date: Date | DateTime
    nav: float
    cash_invested: float
    return_pct: float


class BenchmarkPoint(BaseModel):
    date: Date | DateTime
    return_pct: float


class ExecutionWindowOut(BaseModel):
    ticker: str
    market: str
    currency: str
    market_timezone: str
    display_timezone: str
    ref_day: Date
    market_status: MarketStatus
    execution_start: DateTime | None = None
    execution_end: DateTime | None = None
    training_start: Date
    training_end: Date


class BacktestAllocationOut(BaseModel):
    year: int
    effective_start: Date
    effective_end: Date
    training_start: Date
    training_end: Date
    allocation: dict[str, float]
    metrics: dict[str, AssetMetricsOut] = Field(default_factory=dict)
    global_weights: dict[str, float] = Field(default_factory=dict)
    closeness: dict[str, float] = Field(default_factory=dict)
    indicators: list[str] = Field(default_factory=list)
    has_dividend: bool = False
    constant_criteria: list[str] = Field(default_factory=list)


class BacktestDataWarning(BaseModel):
    ticker: str
    year: int
    training_start: Date
    training_end: Date
    available_start: Date | None = None
    available_end: Date | None = None
    sample_count: int
    action: Literal["excluded", "annualized_short_history"]
    message: str


class BacktestPurchaseEvent(BaseModel):
    ticker: str
    market: str
    timezone: str
    purchased_at_timezone: str | None = None
    purchased_at: Date | DateTime
    currency: str
    price: float
    fx_rate: float
    fx_source: Literal["minute_asof", "hourly_approx", "daily_fallback", "base_currency"]
    fx_as_of: Date | DateTime | None = None
    fx_alignment_note: str | None = None
    price_usd: float
    shares: float
    total_shares: float


class BacktestResponse(BaseModel):
    points: list[BacktestPoint]
    invest_dates: list[Date]
    cumulative_return: float
    annualized_return: float | None
    max_drawdown: float
    final_nav: float
    total_invested: float
    per_asset_final_value: dict[str, float]
    base_currency: str = "USD"
    cash_left: dict[str, float] = Field(default_factory=dict)
    allocation_schedule: list[BacktestAllocationOut] = Field(default_factory=list)
    per_asset_status: dict[str, AssetMarketStatus] = Field(default_factory=dict)
    display_timezone: str | None = None
    data_warnings: list[BacktestDataWarning] = Field(default_factory=list)
    purchase_events: list[BacktestPurchaseEvent] = Field(default_factory=list)
    benchmark: str | None = None
    benchmark_components: dict[str, float] = Field(default_factory=dict)
    benchmark_points: list[BenchmarkPoint] = Field(default_factory=list)
    execution_windows: dict[str, ExecutionWindowOut] = Field(default_factory=dict)
    timings: dict[str, float] = Field(default_factory=dict)


class SettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_source: Literal["yfinance"] = "yfinance"
    benchmark: str = "^GSPC"
    allocation_lookback_days: AllocationLookbackDays = 365


class SearchResult(BaseModel):
    symbol: str
    name: str
    exchange: str
    type: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class HoldingMetricsOut(BaseModel):
    annualized_roi: float
    max_drawdown: float
    volatility: float
    beta: float
    beta_benchmark: str | None = None
    dividend_yield: float | None


class HoldingOut(BaseModel):
    ticker: str
    weight: float
    currency: str = "USD"
    last_price: float | None
    last_price_usd: float | None = None
    daily_change: float | None      # latest day delta over previous close
    period_return: float | None     # cumulative return over the eval window
    metrics: HoldingMetricsOut | None


class EvaluateRequest(BaseModel):
    weights: dict[str, float] = Field(min_length=1)
    range: Range = "1y"
    rf_override: float | None = None
    tz: str | None = None


class EvaluateResponse(BaseModel):
    range: Range
    portfolio: dict
    holdings: list[HoldingOut]
    benchmark: str
    benchmark_components: dict[str, float] = Field(default_factory=dict)
    rf_used: float
    rf_source: str
    rf_window_start: Date | None = None
    rf_window_end: Date | None = None
    per_asset_status: dict[str, AssetMarketStatus] = Field(default_factory=dict)
