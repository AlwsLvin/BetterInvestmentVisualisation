// Mirrors the Pydantic schemas in server/app/schemas.py.

export type Style = 'high_return' | 'low_volatility' | 'balanced'
export type Scheme = 'linear' | 'softmax' | 'power'
export type RangeKey = 'today' | '7d' | '30d' | '90d' | 'ytd' | '1y' | '3y' | '5y'
export type AssetKlinePeriod = 'day' | 'quarter' | 'year'
export type AssetDetailRangeKey = RangeKey | 'dayK' | 'quarterK' | 'yearK'
export type MarketStatus = 'open' | 'closed'
export type AllocationLookbackDays = 30 | 90 | 180 | 365
export type NoticeKind = 'fx_kline_source_change'

export interface PricePoint { date: string; close: number; open?: number | null }
export interface IntradayPoint { datetime: string; close: number }
export interface DividendPoint { date: string; amount: number }
export interface OHLCPoint {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number | null
  period_start?: string | null
  period_end?: string | null
  label?: string | null
}

export interface QuoteSnapshot {
  last_price: number | null
  previous_close: number | null
  change_pct: number | null
  as_of: string | null
  source: string
}

export interface SeriesNotice {
  kind: NoticeKind
  date: string
  text: string
}

export interface AssetSeries {
  symbol: string
  range: AssetDetailRangeKey | string
  points: PricePoint[]
  ohlc?: OHLCPoint[] | null
  dividends: DividendPoint[] | null
  market_status?: MarketStatus | null
  ref_day?: string | null
  market?: string | null
  currency?: string | null
  display_timezone?: string | null
  quote?: QuoteSnapshot | null
  notices?: SeriesNotice[] | null
}

export interface IntradaySeries {
  symbol: string
  period: string
  interval: string
  points: IntradayPoint[]
  market_status?: MarketStatus | null
  ref_day?: string | null
  market?: string | null
  currency?: string | null
  display_timezone?: string | null
  quote?: QuoteSnapshot | null
}

export interface AssetInfo {
  name: string | null
  pe_ratio: number | null
  market_cap: number | null
  week52_high: number | null
  week52_low: number | null
  dividend_yield: number | null
  volume: number | null
  open: number | null
  day_high: number | null
  day_low: number | null
  previous_close: number | null
}

export interface AssetMetrics {
  annualized_roi: number
  max_drawdown: number
  drawdown_duration: number
  recovery_time: number
  volatility: number
  beta: number
  beta_benchmark?: string | null
  dividend_yield: number | null
}

export interface AllocateRequest {
  tickers: string[]
  style?: Style
  scheme?: Scheme
  tau?: number
  power?: number
  floor?: number
  lookback_days?: number
  spread_pct?: number
}

export interface AllocateResponse {
  tickers: string[]
  indicators: string[]
  style: Style
  scheme: Scheme
  has_dividend: boolean
  global_weights: Record<string, number>
  metrics: Record<string, AssetMetrics>
  closeness: Record<string, number>
  allocation: Record<string, number>
  constant_criteria: string[]
}

export interface PlanIn {
  amount: number
  frequency: string
}

export interface AssetMarketStatus {
  market: string
  ref_day: string
  status: MarketStatus
  currency: string
  timezone: string
}

export interface BacktestRequest {
  weights: Record<string, number>
  plan: PlanIn
  range?: RangeKey
  tz?: string | null
}

export interface RollingBacktestRequest {
  tickers: string[]
  style?: Style
  scheme?: Scheme
  tau?: number
  power?: number
  floor?: number
  spread_pct?: number
  plan: PlanIn
  range?: RangeKey
  tz?: string | null
}

export interface BacktestPoint {
  date: string
  nav: number
  cash_invested: number
  return_pct: number
}

export interface BenchmarkPoint {
  date: string
  return_pct: number
}

export interface ExecutionWindow {
  ticker: string
  market: string
  currency: string
  market_timezone: string
  display_timezone: string
  ref_day: string
  market_status: MarketStatus
  execution_start: string | null
  execution_end: string | null
  training_start: string
  training_end: string
}

export interface BacktestAllocation {
  year: number
  effective_start: string
  effective_end: string
  training_start: string
  training_end: string
  allocation: Record<string, number>
  metrics: Record<string, AssetMetrics>
  global_weights: Record<string, number>
  closeness: Record<string, number>
  indicators: string[]
  has_dividend: boolean
  constant_criteria: string[]
}

export interface BacktestDataWarning {
  ticker: string
  year: number
  training_start: string
  training_end: string
  available_start: string | null
  available_end: string | null
  sample_count: number
  action: 'excluded' | 'annualized_short_history'
  message: string
}

export interface BacktestPurchaseEvent {
  ticker: string
  market: string
  timezone: string
  purchased_at_timezone?: string | null
  purchased_at: string
  currency: string
  price: number
  fx_rate: number
  fx_source: 'minute_asof' | 'hourly_approx' | 'daily_fallback' | 'base_currency'
  fx_as_of?: string | null
  fx_alignment_note?: string | null
  price_usd: number
  shares: number
  total_shares: number
}

export interface BacktestResponse {
  points: BacktestPoint[]
  invest_dates: string[]
  cumulative_return: number
  annualized_return: number | null
  max_drawdown: number
  final_nav: number
  total_invested: number
  per_asset_final_value: Record<string, number>
  base_currency: string
  cash_left: Record<string, number>
  allocation_schedule: BacktestAllocation[]
  per_asset_status: Record<string, AssetMarketStatus>
  display_timezone?: string | null
  data_warnings: BacktestDataWarning[]
  purchase_events: BacktestPurchaseEvent[]
  benchmark?: string | null
  benchmark_components: Record<string, number>
  benchmark_points: BenchmarkPoint[]
  execution_windows: Record<string, ExecutionWindow>
  timings: Record<string, number>
}

export interface SettingsModel {
  data_source: 'yfinance'
  benchmark: string
  allocation_lookback_days: AllocationLookbackDays
}

export interface HoldingMetrics {
  annualized_roi: number
  max_drawdown: number
  volatility: number
  beta: number
  beta_benchmark?: string | null
  dividend_yield: number | null
}

export interface Holding {
  ticker: string
  weight: number
  currency: string
  last_price: number | null
  last_price_usd: number | null
  daily_change: number | null
  period_return: number | null
  metrics: HoldingMetrics | null
}

export interface PortfolioMetrics {
  cumulative_return: number
  annualized_return: number
  volatility: number
  max_drawdown: number
  beta: number | null
  alpha: number | null
  sharpe: number
}

export interface EvaluateRequest {
  weights: Record<string, number>
  range?: RangeKey
  rf_override?: number | null
  tz?: string | null
}

export interface EvaluateResponse {
  range: RangeKey
  portfolio: PortfolioMetrics
  holdings: Holding[]
  benchmark: string
  benchmark_components: Record<string, number>
  rf_used: number
  rf_source: 'bil_default' | 'override' | 'constant_fallback'
  rf_window_start?: string | null
  rf_window_end?: string | null
  per_asset_status: Record<string, AssetMarketStatus>
}

export interface SearchResult {
  symbol: string
  name: string
  exchange: string
  type: string
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
}
