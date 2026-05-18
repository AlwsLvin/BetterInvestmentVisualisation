import type {
  AllocateRequest, AllocateResponse,
  AssetInfo, AssetKlinePeriod, AssetSeries, BacktestRequest, BacktestResponse,
  EvaluateRequest, EvaluateResponse, IntradaySeries,
  RangeKey, RollingBacktestRequest, SearchResponse, SettingsModel,
} from './types'

class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail ?? detail } catch { /* noop */ }
    throw new ApiError(r.status, detail)
  }
  return r.json() as Promise<T>
}

const byTime = (a: string, b: string) => new Date(a).getTime() - new Date(b).getTime()
const browserTz = () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const todayTzParam = (range?: RangeKey) =>
  range === 'today' ? `&tz=${encodeURIComponent(browserTz())}` : ''
const withTodayTz = <T extends { range?: RangeKey; tz?: string | null }>(body: T): T =>
  body.range === 'today' ? { ...body, tz: browserTz() } : body

function sortAssetSeries(series: AssetSeries): AssetSeries {
  return {
    ...series,
    points: [...series.points].sort((a, b) => byTime(a.date, b.date)),
    ohlc: series.ohlc ? [...series.ohlc].sort((a, b) => byTime(a.date, b.date)) : series.ohlc,
    dividends: series.dividends
      ? [...series.dividends].sort((a, b) => byTime(a.date, b.date))
      : series.dividends,
  }
}

function sortIntradaySeries(series: IntradaySeries): IntradaySeries {
  return {
    ...series,
    points: [...series.points].sort((a, b) => byTime(a.datetime, b.datetime)),
  }
}

function sortBacktestResponse(data: BacktestResponse): BacktestResponse {
  return {
    ...data,
    points: [...data.points].sort((a, b) => byTime(a.date, b.date)),
    invest_dates: [...data.invest_dates].sort(byTime),
    allocation_schedule: (data.allocation_schedule ?? []).map(row => ({
      ...row,
      effective_start: row.effective_start ?? row.training_start,
      effective_end: row.effective_end ?? row.training_end,
      metrics: row.metrics ?? {},
      global_weights: row.global_weights ?? {},
      closeness: row.closeness ?? {},
      indicators: row.indicators ?? [],
      has_dividend: row.has_dividend ?? false,
      constant_criteria: row.constant_criteria ?? [],
    })),
    data_warnings: data.data_warnings ?? [],
    purchase_events: data.purchase_events ?? [],
    benchmark: data.benchmark ?? null,
    benchmark_components: data.benchmark_components ?? {},
    benchmark_points: [...(data.benchmark_points ?? [])].sort((a, b) => byTime(a.date, b.date)),
    execution_windows: data.execution_windows ?? {},
    timings: data.timings ?? {},
  }
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),
  asset: (symbol: string, range: RangeKey = '1y', ohlc = false, intraday = false) =>
    request<AssetSeries>(
      `/api/asset/${encodeURIComponent(symbol)}?range=${range}${ohlc ? '&ohlc=true' : ''}${intraday ? '&intraday=true' : ''}${todayTzParam(range)}`,
    ).then(sortAssetSeries),
  assetKline: (symbol: string, period: AssetKlinePeriod = 'day') =>
    request<AssetSeries>(
      `/api/asset-kline/${encodeURIComponent(symbol)}?period=${period}`,
    ).then(sortAssetSeries),
  assetInfo: (symbol: string) =>
    request<AssetInfo>(`/api/asset/${encodeURIComponent(symbol)}/info`),
  index: (code: string, range: RangeKey = '1y') =>
    request<AssetSeries>(`/api/index/${encodeURIComponent(code)}?range=${range}${todayTzParam(range)}`)
      .then(sortAssetSeries),
  indexIntraday: (code: string) =>
    request<IntradaySeries>(`/api/intraday/index/${encodeURIComponent(code)}?tz=${encodeURIComponent(browserTz())}`)
      .then(sortIntradaySeries),
  fxIntraday: (symbol: string) =>
    request<IntradaySeries>(
      `/api/intraday/fx/${encodeURIComponent(symbol)}?tz=${encodeURIComponent(browserTz())}`,
    )
      .then(sortIntradaySeries),
  fx: (symbol: string, range: RangeKey = 'today') =>
    request<AssetSeries>(
      `/api/fx/${encodeURIComponent(symbol)}?range=${range}${todayTzParam('today')}`,
    ).then(sortAssetSeries),
  fxKline: (symbol: string, period: AssetKlinePeriod = 'day') =>
    request<AssetSeries>(
      `/api/fx-kline/${encodeURIComponent(symbol)}?period=${period}&tz=${encodeURIComponent(browserTz())}`,
    ).then(sortAssetSeries),
  allocate: (body: AllocateRequest) =>
    request<AllocateResponse>('/api/portfolio/allocate', {
      method: 'POST', body: JSON.stringify(body),
    }),
  backtest: (body: BacktestRequest) =>
    request<BacktestResponse>('/api/backtest', {
      method: 'POST', body: JSON.stringify(withTodayTz(body)),
    }).then(sortBacktestResponse),
  rollingBacktest: (body: RollingBacktestRequest) =>
    request<BacktestResponse>('/api/backtest/rolling-allocation', {
      method: 'POST', body: JSON.stringify(withTodayTz(body)),
    }).then(sortBacktestResponse),
  evaluate: (body: EvaluateRequest) =>
    request<EvaluateResponse>('/api/portfolio/evaluate', {
      method: 'POST', body: JSON.stringify(withTodayTz(body)),
    }),
  getSettings: () => request<SettingsModel>('/api/settings'),
  putSettings: (body: SettingsModel) =>
    request<SettingsModel>('/api/settings', {
      method: 'PUT', body: JSON.stringify(body),
    }),
  search: (q: string, limit = 50) =>
    request<SearchResponse>(
      `/api/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
}

export { ApiError }
