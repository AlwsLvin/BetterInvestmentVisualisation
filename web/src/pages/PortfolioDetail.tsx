import { Fragment, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '@/api/client'
import type {
  BacktestAllocation,
  BacktestDataWarning,
  BacktestPurchaseEvent,
  ExecutionWindow,
  Holding,
  RangeKey,
} from '@/api/types'
import { BenchmarkPicker } from '@/components/BenchmarkPicker'
import { InfoTooltip } from '@/components/InfoTooltip'
import { useView } from '@/stores/view'
import { useWatchlist, DEFAULT_WATCHLIST_ID } from '@/stores/watchlist'
import { fmtSignedPct, fmtPct, fmtNumber, trendColor } from '@/utils/format'
import { holdingReturnSeries, returnSeriesFromPoints } from '@/utils/performance'
import { isIndexSymbol } from '@/utils/symbols'
import { benchmarkDetailTitle, formatBenchmarkComponents } from '@/utils/benchmark'
import {
  METRIC_EXPLANATIONS,
  indicatorExplanation,
  withContext,
} from '@/utils/metricExplanations'

const RANGES: RangeKey[] = ['today', '7d', '30d', '90d', 'ytd', '1y', '3y', '5y']
const RANGE_LABEL: Record<RangeKey, string> = {
  today: '当日', '7d': '7天', '30d': '30天', '90d': '90天',
  ytd: '年初至今',
  '1y': '1年', '3y': '3年', '5y': '5年',
}
const RANGE_TITLE: Partial<Record<RangeKey, string>> = {
  ytd: `当年至今 (YTD)：${new Date().getFullYear()}-01-01 至今`,
  '1y': '回溯 1 年：一年前至今',
}
const ALL_HOLDINGS = '__all__'
const HOLDING_DETAIL_PAGE_SIZE = 8

type HoldingCostBasis = {
  avgLocal: number
  avgUsd: number
  shares: number
}

type HoldingDetailRow = (
  | { kind: 'event'; ticker: string; event: BacktestPurchaseEvent }
  | { kind: 'empty'; ticker: string; reason: string }
)

export function PortfolioDetail() {
  const initialRange = useView(s => s.view.type === 'portfolio' ? s.view.range : '1y')
  const initialBenchmark = useView(s =>
    s.view.type === 'portfolio' ? s.view.benchmarkSymbol : undefined,
  )
  const returnTab = useView(s => s.view.type === 'portfolio' ? s.view.returnTab : 'watchlist')
  const goHome = useView(s => s.goHome)
  const goAsset = useView(s => s.goAsset)
  const activeId = useWatchlist(s => s.activeId || DEFAULT_WATCHLIST_ID)
  const watchlist = useWatchlist(s => s.watchlists[s.activeId] ?? s.watchlists[DEFAULT_WATCHLIST_ID])
  const plan = useWatchlist(s => s.plans[s.activeId] ?? s.plans[DEFAULT_WATCHLIST_ID])
  const prefs = useWatchlist(s => s.prefs[s.activeId] ?? s.prefs[DEFAULT_WATCHLIST_ID])

  const [range, setRange] = useState<RangeKey>(initialRange)
  const [benchmarkSymbol, setBenchmarkSymbol] = useState<string | undefined>(initialBenchmark)
  const [useOverride, setUseOverride] = useState(false)
  const [rfDraft, setRfDraft] = useState(0.03)
  const [showHoldingDetails, setShowHoldingDetails] = useState(false)
  const [showMetricHistory, setShowMetricHistory] = useState(false)
  const [holdingFilter, setHoldingFilter] = useState(ALL_HOLDINGS)
  const [holdingDetailsPage, setHoldingDetailsPage] = useState(1)
  const [metricDetailsPage, setMetricDetailsPage] = useState(1)
  const settingsQ = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.getSettings(),
    staleTime: 0,
  })
  const allocationLookbackDays = settingsQ.data?.allocation_lookback_days ?? 365

  const backtestQ = useQuery({
    queryKey: ['rolling-backtest', activeId, watchlist.tickers, prefs.style, prefs.scheme,
               prefs.tau, prefs.power, prefs.floor, plan.amount, plan.frequency, range,
               allocationLookbackDays],
    queryFn: () => api.rollingBacktest({
      tickers: watchlist.tickers,
      style: prefs.style, scheme: prefs.scheme,
      tau: prefs.tau, power: prefs.power, floor: prefs.floor,
      plan: { amount: plan.amount, frequency: plan.frequency },
      range,
    }),
    enabled: watchlist.tickers.length > 0,
    refetchInterval: range === 'today' ? 60 * 1000 : false,
  })

  const currentSchedule = backtestQ.data?.allocation_schedule.at(-1)
  const currentAllocation = currentSchedule?.allocation

  const evalQ = useQuery({
    queryKey: ['evaluate', currentAllocation, range,
               useOverride ? rfDraft : null],
    queryFn: () => api.evaluate({
      weights: currentAllocation!,
      range,
      rf_override: useOverride ? rfDraft : null,
    }),
    enabled: !!currentAllocation,
    refetchInterval: range === 'today' ? 60 * 1000 : false,
  })

  const benchmarkQ = useQuery({
    queryKey: ['benchmark-series', benchmarkSymbol, range],
    queryFn: () => isIndexSymbol(benchmarkSymbol!)
      ? api.index(benchmarkSymbol!, range)
      : api.asset(benchmarkSymbol!, range),
    enabled: !!benchmarkSymbol,
    refetchInterval: range === 'today' ? 60 * 1000 : false,
  })

  const portfolio = evalQ.data?.portfolio
  const statusByTicker = evalQ.data?.per_asset_status ?? {}
  const dataWarnings = backtestQ.data?.data_warnings ?? []
  const purchaseEvents = backtestQ.data?.purchase_events ?? []
  const purchaseEventsByTicker = new Map<string, BacktestPurchaseEvent[]>()
  for (const event of purchaseEvents) {
    const rows = purchaseEventsByTicker.get(event.ticker) ?? []
    rows.push(event)
    purchaseEventsByTicker.set(event.ticker, rows)
  }
  const costBasisByTicker = new Map<string, HoldingCostBasis>()
  for (const [ticker, events] of purchaseEventsByTicker) {
    const costBasis = costBasisForEvents(events)
    if (costBasis != null) costBasisByTicker.set(ticker, costBasis)
  }
  const sortedHoldings = evalQ.data?.holdings
    .slice()
    .sort((a, b) => b.weight - a.weight) ?? []
  const holdingDetailRows = showHoldingDetails
    ? buildHoldingDetailRows(sortedHoldings, purchaseEventsByTicker, holdingFilter, plan.amount)
    : []
  const holdingDetailTotalPages = Math.max(1, Math.ceil(holdingDetailRows.length / HOLDING_DETAIL_PAGE_SIZE))
  const holdingDetailPage = Math.min(holdingDetailsPage, holdingDetailTotalPages)
  const visibleHoldingDetailRows = holdingDetailRows.slice(
    (holdingDetailPage - 1) * HOLDING_DETAIL_PAGE_SIZE,
    holdingDetailPage * HOLDING_DETAIL_PAGE_SIZE,
  )
  const benchmark = benchmarkQ.data
    ? holdingReturnSeries(benchmarkQ.data.points, backtestQ.data?.points[0]?.date)
    : null
  const defaultBenchmark = backtestQ.data?.benchmark_points.length
    ? returnSeriesFromPoints(backtestQ.data.benchmark_points)
    : null
  const activeBenchmark = benchmarkSymbol ? benchmark : defaultBenchmark
  const activeBenchmarkTitle = benchmarkDetailTitle({
    customSymbol: benchmarkSymbol,
    components: backtestQ.data?.benchmark_components,
    fallbackLabel: backtestQ.data?.benchmark,
  })

  useEffect(() => {
    setHoldingDetailsPage(1)
  }, [holdingFilter, showHoldingDetails, range, purchaseEvents.length])

  useEffect(() => {
    if (!showHoldingDetails) setHoldingFilter(ALL_HOLDINGS)
  }, [showHoldingDetails])

  useEffect(() => {
    if (holdingFilter === ALL_HOLDINGS) return
    if (!sortedHoldings.some(h => h.ticker === holdingFilter)) {
      setHoldingFilter(ALL_HOLDINGS)
    }
  }, [holdingFilter, sortedHoldings])

  useEffect(() => {
    setMetricDetailsPage(1)
  }, [showMetricHistory, range, backtestQ.data?.allocation_schedule.length])

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="grid min-h-screen w-full grid-rows-[auto_minmax(0,1fr)]
                 gap-3 p-3 safe-area-top safe-area-bottom
                 lg:h-screen lg:gap-4 lg:p-4"
    >
      <header className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={goHome}
          aria-label="返回"
          className="grid h-tap w-tap shrink-0 place-items-center rounded-lg
                     border border-border bg-bg-card text-ink-dim
                     hover:bg-bg-elev hover:text-ink
                     focus:outline-none focus:ring-2 focus:ring-accent"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24"
               stroke="currentColor" strokeWidth={2}>
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>

        <div className="min-w-0 flex-1">
          <div className="text-xs uppercase tracking-wider text-ink-dim">
            自选组合 · 详情
          </div>
          <h1 className="text-xl font-semibold sm:text-2xl">
            {watchlist.name}
            <span className="ml-2 text-xs text-ink-faint font-normal">
              {watchlist.tickers.length} 个标的 · 风格：
              {prefs.style === 'high_return' ? '高回报' : '低波动'}
            </span>
          </h1>
        </div>

        <div className="flex gap-1 overflow-x-auto scrollbar-hide">
          {RANGES.map(r => {
            const active = r === range
            return (
              <button
                key={r}
                onClick={() => setRange(r)}
                title={RANGE_TITLE[r]}
                className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium
                            transition-colors min-h-[32px]
                            ${active
                              ? 'bg-accent text-white'
                              : 'text-ink-dim hover:bg-bg-elev hover:text-ink'}`}
              >
                {RANGE_LABEL[r]}
              </button>
            )
          })}
        </div>
      </header>

      <div className="grid h-full grid-rows-[auto_auto_minmax(0,1fr)] gap-3 overflow-hidden
                      lg:grid-cols-[minmax(420px,0.85fr)_minmax(0,1.85fr)]
                      lg:grid-rows-1 lg:gap-4">
        <div className="flex min-h-0 flex-col gap-3 overflow-hidden
                        lg:grid lg:grid-rows-[minmax(260px,auto)_minmax(0,1fr)]">
        <section className="flex min-h-[180px] flex-col gap-3 rounded-xl
                            border border-border bg-bg-card p-4 overflow-auto
                            lg:min-h-[260px] lg:max-h-[44vh]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[11px] uppercase tracking-wider text-ink-faint">
              买入持有评价
            </div>
            <BenchmarkPicker
              value={benchmarkSymbol}
              onSelect={setBenchmarkSymbol}
              onClear={() => setBenchmarkSymbol(undefined)}
            />
          </div>

          {(evalQ.isLoading || backtestQ.isLoading) && (
            <div className="grid min-h-[96px] place-items-start text-sm text-ink-faint">
              计算中…
            </div>
          )}
          {evalQ.isError && (
            <div className="text-sm text-accent-down">
              {(evalQ.error as Error).message}
            </div>
          )}
          {backtestQ.isError && (
            <div className="text-sm text-accent-down">
              滚动分配 / 回测失败：{(backtestQ.error as Error).message}
            </div>
          )}
          {portfolio && evalQ.data && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <Metric
                  label="持有累计"
                  value={fmtSignedPct(portfolio.cumulative_return)}
                  colorClass={trendColor(portfolio.cumulative_return)}
                  help={METRIC_EXPLANATIONS.holdingCumulative}
                />
                <Metric
                  label="持有年化"
                  value={range === 'today' ? '—' : fmtSignedPct(portfolio.annualized_return)}
                  colorClass={range === 'today' ? 'text-ink-faint' : trendColor(portfolio.annualized_return)}
                  help={METRIC_EXPLANATIONS.holdingAnnualized}
                />
                <Metric
                  label="定投最新"
                  value={backtestQ.data ? fmtSignedPct(backtestQ.data.cumulative_return) : '—'}
                  colorClass={trendColor(backtestQ.data?.cumulative_return ?? 0)}
                  help={METRIC_EXPLANATIONS.dcaLatest}
                />
                <Metric
                  label="定投资金年化"
                  value={backtestQ.data?.annualized_return == null
                    ? '—'
                    : fmtSignedPct(backtestQ.data.annualized_return)}
                  colorClass={backtestQ.data?.annualized_return == null
                    ? 'text-ink-faint'
                    : trendColor(backtestQ.data.annualized_return)}
                  help={METRIC_EXPLANATIONS.dcaAnnualized}
                />
                <Metric
                  label="标准差 σ"
                  value={fmtPct(portfolio.volatility, 2)}
                  help={METRIC_EXPLANATIONS.volatility}
                />
                <Metric
                  label="最大回撤"
                  value={fmtPct(portfolio.max_drawdown, 2)}
                  colorClass="text-accent-down"
                  help={METRIC_EXPLANATIONS.maxDrawdown}
                />
                {activeBenchmark && (
                  <>
                    <Metric
                      label="基准最新"
                      value={fmtSignedPct(activeBenchmark.cumulativeReturn)}
                      colorClass={trendColor(activeBenchmark.cumulativeReturn)}
                      help={withContext(METRIC_EXPLANATIONS.benchmarkLatest, activeBenchmarkTitle)}
                    />
                    <Metric
                      label="基准最大回撤"
                      value={fmtPct(activeBenchmark.maxDrawdown, 2)}
                      colorClass="text-accent-down"
                      help={withContext(METRIC_EXPLANATIONS.benchmarkMaxDrawdown, activeBenchmarkTitle)}
                    />
                  </>
                )}
                <Metric
                  label="Beta β"
                  value={portfolio.beta == null ? '—' : portfolio.beta.toFixed(3)}
                  colorClass={portfolio.beta == null ? 'text-ink-faint' : ''}
                  help={METRIC_EXPLANATIONS.beta}
                />
                <Metric
                  label="Alpha α"
                  value={portfolio.alpha == null ? '—' : fmtSignedPct(portfolio.alpha)}
                  colorClass={portfolio.alpha == null ? 'text-ink-faint' : trendColor(portfolio.alpha)}
                  help={METRIC_EXPLANATIONS.alpha}
                />
                <Metric
                  label="Sharpe"
                  value={portfolio.sharpe.toFixed(3)}
                  colorClass={trendColor(portfolio.sharpe)}
                  help={METRIC_EXPLANATIONS.sharpe}
                />
              </div>

              <div className="rounded-md border border-border bg-bg-elev/50 p-3 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1 text-ink-dim">
                    无风险利率 R<sub>f</sub>
                    <InfoTooltip content={METRIC_EXPLANATIONS.riskFreeRate} />
                  </span>
                  <span className="font-mono text-ink">
                    {fmtPct(evalQ.data.rf_used, 2)}
                  </span>
                </div>
                <div className="mt-0.5 text-[11px] text-ink-faint">
                  来源：{rfSourceLabel(evalQ.data.rf_source)}
                  {evalQ.data.rf_window_start && evalQ.data.rf_window_end && (
                    <span className="ml-1">
                      {evalQ.data.rf_window_start} 至 {evalQ.data.rf_window_end}
                    </span>
                  )}
                </div>
                <label className="mt-2 flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={useOverride}
                    onChange={e => setUseOverride(e.target.checked)}
                    className="accent-accent"
                  />
                  <span className="text-ink-dim">手动指定 R<sub>f</sub></span>
                  {useOverride && (
                    <input
                      type="number"
                      min={0} max={0.20} step={0.005}
                      value={rfDraft}
                      onChange={e => setRfDraft(Number(e.target.value))}
                      className="ml-auto w-20 rounded border border-border
                                 bg-bg-elev px-2 py-1 font-mono text-xs"
                    />
                  )}
                </label>
              </div>
              <div className="text-[11px] text-ink-faint">
                Beta 基准：{formatBenchmarkComponents(
                  evalQ.data.benchmark_components,
                  evalQ.data.benchmark,
                )}
                {currentSchedule && (
                  <span className="ml-2">
                    权重执行：{currentSchedule.effective_start} 至 {currentSchedule.effective_end}
                  </span>
                )}
                {currentSchedule && (
                  <span className="ml-2">
                    指标训练：{currentSchedule.training_start} 至 {currentSchedule.training_end}
                  </span>
                )}
                {activeBenchmark && (
                  <span className="ml-2" title={activeBenchmarkTitle}>
                    图表基准：基准
                  </span>
                )}
                {(portfolio.beta == null || portfolio.alpha == null) && (
                  <span className="ml-2 text-accent-down">
                    当日跨市场基准重合不足，Beta/Alpha 暂不计算
                  </span>
                )}
              </div>
              {benchmarkQ.isError && (
                <div className="text-xs text-accent-down">
                  基准加载失败：{(benchmarkQ.error as Error).message}
                </div>
              )}
            </>
          )}
        </section>
        <MetricsDetailCard
          schedules={backtestQ.data?.allocation_schedule ?? []}
          warnings={dataWarnings}
          executionWindows={backtestQ.data?.execution_windows ?? {}}
          range={range}
          onOpenDetails={() => setShowMetricHistory(true)}
        />
        </div>

        <section className="flex flex-col rounded-xl border border-border
                            bg-bg-card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2
                          border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowHoldingDetails(v => !v)}
                className={`rounded-md border px-2 py-1 text-[11px] font-medium
                            transition-colors focus:outline-none focus:ring-2 focus:ring-accent
                            ${showHoldingDetails
                              ? 'border-accent bg-accent/10 text-accent'
                              : 'border-border bg-bg-elev/40 text-ink-dim hover:text-ink'}`}
              >
                详情
              </button>
              {showHoldingDetails && (
                <select
                  value={holdingFilter}
                  onChange={event => setHoldingFilter(event.target.value)}
                  className="h-8 rounded-md border border-border bg-bg-elev px-2
                             text-xs text-ink focus:outline-none focus:ring-2
                             focus:ring-accent"
                  aria-label="筛选持仓成交明细"
                >
                  <option value={ALL_HOLDINGS}>全部</option>
                  {sortedHoldings.map(h => (
                    <option key={h.ticker} value={h.ticker}>{h.ticker}</option>
                  ))}
                </select>
              )}
              <span className="text-[11px] uppercase tracking-wider text-ink-faint">
                持仓明细
              </span>
            </div>
            <DataWarningsNotice warnings={dataWarnings} />
          </div>
          <div className={showHoldingDetails ? 'flex min-h-0 flex-1 flex-col' : 'overflow-auto'}>
            {evalQ.data && !showHoldingDetails && (
              <table className="w-full min-w-[1120px] text-sm">
                <thead className="bg-bg-elev/50">
                  <tr className="text-[11px] uppercase tracking-wider text-ink-faint">
                    <Th>标的</Th>
                    <Th right help={METRIC_EXPLANATIONS.weight}>权重</Th>
                    <Th right help={METRIC_EXPLANATIONS.costPrice}>成本价</Th>
                    <Th right help={METRIC_EXPLANATIONS.latestPrice}>最新价</Th>
                    <Th right help={METRIC_EXPLANATIONS.currency}>币种</Th>
                    <Th right help={METRIC_EXPLANATIONS.usdConverted}>USD折算</Th>
                    <Th right help={METRIC_EXPLANATIONS.dailyChange}>当日涨跌</Th>
                    <Th
                      right
                      help={withContext(
                        METRIC_EXPLANATIONS.periodReturnUsd,
                        '无实际成交时为空；后端返回的买入持有 period_return 保留但此处不使用。',
                      )}
                    >
                      区间收益 (USD)
                    </Th>
                    <Th right help={METRIC_EXPLANATIONS.beta}>β</Th>
                    <Th right help={METRIC_EXPLANATIONS.volatility}>σ</Th>
                    <Th right help={METRIC_EXPLANATIONS.maxDrawdown}>MDD</Th>
                  </tr>
                </thead>
                <tbody>
                  {sortedHoldings
                    .map(h => {
                      const assetStatus = statusByTicker[h.ticker]
                      const costBasis = costBasisByTicker.get(h.ticker)
                      const costReturn = h.last_price_usd != null && costBasis
                        ? h.last_price_usd / costBasis.avgUsd - 1
                        : null
                      return (
                      <Fragment key={h.ticker}>
                        <tr className="border-t border-border hover:bg-bg-elev/40 transition-colors">
                          <td className="px-4 py-2">
                            <div className="flex flex-col gap-1">
                              <button
                                type="button"
                                onClick={() => goAsset(h.ticker, {
                                  type: 'portfolio',
                                  returnTab,
                                  range,
                                  benchmarkSymbol,
                                })}
                                className="w-fit font-mono text-sm hover:text-accent
                                           focus:outline-none focus:text-accent"
                              >
                                {h.ticker}
                              </button>
                              {range === 'today' && assetStatus && (
                                <StatusBadge
                                  status={assetStatus.status}
                                  refDay={assetStatus.ref_day}
                                />
                              )}
                            </div>
                          </td>
                          <Td right mono>{fmtPct(h.weight, 1)}</Td>
                          <Td right mono>{costBasis != null ? fmtNumber(costBasis.avgLocal, 2) : '—'}</Td>
                          <Td right mono>{h.last_price != null ? fmtNumber(h.last_price, 2) : '—'}</Td>
                          <Td right mono>{h.currency}</Td>
                          <Td right mono>{h.last_price_usd != null ? fmtNumber(h.last_price_usd, 2) : '—'}</Td>
                          <Td right mono className={trendColor(h.daily_change ?? 0)}>
                            {h.daily_change != null ? fmtSignedPct(h.daily_change) : '—'}
                          </Td>
                          <Td right mono className={trendColor(costReturn ?? 0)}>
                            {costReturn != null ? fmtSignedPct(costReturn) : '—'}
                          </Td>
                          <Td right mono>
                            {h.metrics ? (
                              <span title={h.metrics.beta_benchmark ? `Beta 基准：${h.metrics.beta_benchmark}` : undefined}>
                                {h.metrics.beta.toFixed(2)}
                                {h.metrics.beta_benchmark && (
                                  <span className="ml-1 text-[10px] text-ink-faint">
                                    {h.metrics.beta_benchmark}
                                  </span>
                                )}
                              </span>
                            ) : '—'}
                          </Td>
                          <Td right mono>{h.metrics ? fmtPct(h.metrics.volatility, 1) : '—'}</Td>
                          <Td right mono className="text-accent-down">
                            {h.metrics ? fmtPct(h.metrics.max_drawdown, 1) : '—'}
                          </Td>
                        </tr>
                      </Fragment>
                    )})}
                </tbody>
              </table>
            )}
            {evalQ.data && showHoldingDetails && (
              <>
                <div className="min-h-0 flex-1 overflow-x-auto">
                  <HoldingDetailTable rows={visibleHoldingDetailRows} />
                </div>
                <Pager
                  page={holdingDetailPage}
                  totalPages={holdingDetailTotalPages}
                  onPageChange={setHoldingDetailsPage}
                  className="border-t border-border px-4 py-3"
                />
              </>
            )}
            {!evalQ.data && (
              <div className="grid h-32 place-items-center text-ink-faint text-sm">
                {backtestQ.isLoading ? '加载滚动权重…' : '加载评价…'}
              </div>
            )}
          </div>
        </section>
      </div>
      {showMetricHistory && (
        <MetricsDetailOverlay
          schedules={backtestQ.data?.allocation_schedule ?? []}
          warnings={dataWarnings}
          executionWindows={backtestQ.data?.execution_windows ?? {}}
          range={range}
          page={metricDetailsPage}
          onPageChange={setMetricDetailsPage}
          onClose={() => setShowMetricHistory(false)}
        />
      )}
    </motion.div>
  )
}


function MetricsDetailCard({
  schedules,
  warnings,
  executionWindows,
  range,
  onOpenDetails,
}: {
  schedules: BacktestAllocation[]
  warnings: BacktestDataWarning[]
  executionWindows: Record<string, ExecutionWindow>
  range: RangeKey
  onOpenDetails: () => void
}) {
  const ordered = schedules.slice().sort((a, b) =>
    new Date(b.effective_end).getTime() - new Date(a.effective_end).getTime(),
  )
  const visible = ordered.slice(0, 1)

  return (
    <section className="flex min-h-[280px] flex-col rounded-xl border border-border
                        bg-bg-card overflow-hidden lg:min-h-0">
      <div className="flex flex-wrap items-center justify-between gap-2
                      border-b border-border px-4 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-ink-faint">
            具体指标
          </div>
          {visible[0] && (
            <div className="mt-0.5 text-[11px] text-ink-dim">
              执行 {visible[0].effective_start} 至 {visible[0].effective_end}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={onOpenDetails}
          className="rounded-md border border-border bg-bg-elev/40 px-2 py-1
                     text-[11px] font-medium text-ink-dim hover:text-ink
                     focus:outline-none focus:ring-2 focus:ring-accent"
        >
          展开
        </button>
      </div>
      <div className="min-h-0 overflow-auto p-3">
        {visible.length === 0 ? (
          <div className="grid h-24 place-items-center text-xs text-ink-faint">
            暂无指标明细。
          </div>
        ) : (
          <div className="grid gap-3">
            {visible.map(schedule => (
              <ScheduleMetrics
                key={`${schedule.effective_start}:${schedule.effective_end}`}
                schedule={schedule}
                warnings={warnings.filter(w =>
                  w.training_start === schedule.training_start
                  && w.training_end === schedule.training_end,
                )}
                executionWindows={range === 'today' ? executionWindows : {}}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}


function MetricsDetailOverlay({
  schedules,
  warnings,
  executionWindows,
  range,
  page,
  onPageChange,
  onClose,
}: {
  schedules: BacktestAllocation[]
  warnings: BacktestDataWarning[]
  executionWindows: Record<string, ExecutionWindow>
  range: RangeKey
  page: number
  onPageChange: (page: number) => void
  onClose: () => void
}) {
  const ordered = schedules.slice().sort((a, b) =>
    new Date(b.effective_end).getTime() - new Date(a.effective_end).getTime(),
  )
  const totalPages = Math.max(1, ordered.length)
  const currentPage = Math.min(page, totalPages)
  const schedule = ordered[currentPage - 1]

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-label="具体指标详情"
      className="fixed inset-0 z-50 flex flex-col safe-area-top safe-area-bottom"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
    >
      <button
        type="button"
        aria-label="关闭具体指标详情"
        className="absolute inset-0 bg-bg/85 backdrop-blur-md"
        onClick={onClose}
      />

      <motion.section
        initial={{ opacity: 0, y: 14, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 14, scale: 0.98 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="relative mx-auto mt-8 flex max-h-[84vh]
                   w-[min(1100px,calc(100vw-2rem))] flex-col overflow-hidden
                   rounded-xl border border-border bg-bg-card shadow-2xl
                   shadow-black/40 sm:mt-12"
      >
        <header className="flex flex-wrap items-center justify-between gap-2
                           border-b border-border px-4 py-3">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-ink-faint">
              具体指标
            </div>
            {schedule && (
              <div className="mt-0.5 text-[11px] text-ink-dim">
                执行 {schedule.effective_start} 至 {schedule.effective_end}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="grid h-8 w-8 place-items-center rounded-md text-ink-faint
                       hover:bg-bg-elev hover:text-ink focus:outline-none
                       focus:ring-2 focus:ring-accent"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" strokeWidth={2.4}>
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto p-3">
          {schedule ? (
            <ScheduleMetrics
              schedule={schedule}
              warnings={warnings.filter(w =>
                w.training_start === schedule.training_start
                && w.training_end === schedule.training_end,
              )}
              executionWindows={range === 'today' ? executionWindows : {}}
            />
          ) : (
            <div className="grid h-24 place-items-center text-xs text-ink-faint">
              暂无指标明细。
            </div>
          )}
        </div>
        <Pager
          page={currentPage}
          totalPages={totalPages}
          onPageChange={onPageChange}
          className="border-t border-border px-4 py-3"
        />
      </motion.section>
    </motion.div>
  )
}


function ScheduleMetrics({
  schedule,
  warnings,
  executionWindows,
}: {
  schedule: BacktestAllocation
  warnings: BacktestDataWarning[]
  executionWindows: Record<string, ExecutionWindow>
}) {
  const rows = Object.entries(schedule.metrics)
    .sort(([a], [b]) => (schedule.allocation[b] ?? 0) - (schedule.allocation[a] ?? 0))

  return (
    <div className="rounded-lg border border-border bg-bg-elev/25">
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
        <div>
          <div className="text-xs font-medium text-ink">
            权重窗口 {schedule.effective_start} 至 {schedule.effective_end}
          </div>
          <div className="mt-0.5 text-[11px] text-ink-faint">
            训练数据 {schedule.training_start} 至 {schedule.training_end}
          </div>
          {Object.keys(executionWindows).length > 0 && (
            <div className="mt-0.5 text-[10px] text-ink-faint">
              训练窗口为后端按设置回滚窗口计算的历史日线范围，不是浏览器时区换算。
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-1">
          <span className="inline-flex items-center gap-1 rounded border border-border
                           bg-bg-card px-1.5 py-0.5 text-[10px] text-ink-faint">
            FAHP指标权重
            <InfoTooltip
              content="这些是投资风格对应的评分权重，不是该窗口里所有股票的平均收益或平均回撤；每个标的的真实训练指标在下方表格。"
              className="scale-90"
            />
          </span>
          {Object.entries(schedule.global_weights).map(([name, weight]) => {
            const help = indicatorExplanation(name)
            return (
              <span key={name}
                    className="inline-flex items-center gap-1 rounded border border-border
                               bg-bg-card px-1.5 py-0.5 text-[10px] text-ink-dim">
                {indicatorLabel(name)}权重 {fmtPct(weight, 1)}
                {help && <InfoTooltip content={help} className="scale-90" />}
              </span>
            )
          })}
        </div>
      </div>
      {rows.length > 0 && (
        <MetricSummary rows={rows.map(([_ticker, metrics]) => metrics)} />
      )}
      {warnings.length > 0 && (
        <div className="border-t border-border px-3 py-2">
          <ScheduleWarnings warnings={warnings} />
        </div>
      )}
      {Object.keys(executionWindows).length > 0 && (
        <TodayExecutionWindows windows={executionWindows} />
      )}
      {rows.length > 0 ? (
        <div className="overflow-x-auto border-t border-border">
          <table className="w-full min-w-[920px] text-xs">
            <thead className="bg-bg-elev/50 text-[10px] uppercase tracking-wider text-ink-faint">
              <tr>
                <Th>标的</Th>
                <Th right help={METRIC_EXPLANATIONS.weight}>权重</Th>
                <Th right help={METRIC_EXPLANATIONS.closeness}>贴近度</Th>
                <Th right help={METRIC_EXPLANATIONS.annualizedRoi}>年化收益</Th>
                <Th right help={METRIC_EXPLANATIONS.dividendYield}>股息率</Th>
                <Th right help={METRIC_EXPLANATIONS.maxDrawdown}>MDD</Th>
                <Th right help={METRIC_EXPLANATIONS.drawdownDuration}>回撤天数</Th>
                <Th right help={METRIC_EXPLANATIONS.recoveryTime}>恢复天数</Th>
                <Th right help={METRIC_EXPLANATIONS.volatility}>波动率</Th>
                <Th right help={METRIC_EXPLANATIONS.beta}>Beta</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([ticker, metrics]) => {
                const warning = warnings.find(w => w.ticker === ticker)
                return (
                  <tr key={`${schedule.effective_start}-${schedule.effective_end}-${ticker}`}
                      className="border-t border-border/70">
                    <td className="px-4 py-2">
                      <div className="font-mono text-ink">{ticker}</div>
                      {warning && (
                        <div className="mt-0.5 text-[10px] text-accent-down">
                          {warningLabel(warning.action)}
                        </div>
                      )}
                    </td>
                    <Td right mono>{fmtPct(schedule.allocation[ticker] ?? 0, 1)}</Td>
                    <Td right mono>{fmtNumber(schedule.closeness[ticker] ?? 0, 3)}</Td>
                    <Td right mono className={trendColor(metrics.annualized_roi)}>
                      {fmtSignedPct(metrics.annualized_roi)}
                    </Td>
                    <Td right mono>
                      {metrics.dividend_yield == null ? '—' : fmtPct(metrics.dividend_yield, 2)}
                    </Td>
                    <Td right mono className="text-accent-down">
                      {fmtPct(metrics.max_drawdown, 1)}
                    </Td>
                    <Td right mono>{fmtNumber(metrics.drawdown_duration, 0)}</Td>
                    <Td right mono>{fmtNumber(metrics.recovery_time, 0)}</Td>
                    <Td right mono>{fmtPct(metrics.volatility, 1)}</Td>
                    <Td right mono>
                      {metrics.beta.toFixed(2)}
                      {metrics.beta_benchmark && (
                        <span className="ml-1 text-[10px] text-ink-faint">
                          {metrics.beta_benchmark}
                        </span>
                      )}
                    </Td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="border-t border-border px-3 py-4 text-xs text-ink-faint">
          该窗口内没有可用指标。
        </div>
      )}
    </div>
  )
}


function MetricSummary({
  rows,
}: {
  rows: BacktestAllocation['metrics'][string][]
}) {
  const avgAnnualized = average(rows.map(row => row.annualized_roi))
  const avgMdd = average(rows.map(row => row.max_drawdown))
  const maxMdd = Math.max(...rows.map(row => row.max_drawdown))
  const avgVolatility = average(rows.map(row => row.volatility))

  return (
    <div className="grid gap-2 border-t border-border px-3 py-2
                    sm:grid-cols-4">
      <SummaryPill
        label="平均年化收益"
        value={fmtSignedPct(avgAnnualized)}
        className={trendColor(avgAnnualized)}
      />
      <SummaryPill
        label="平均 MDD"
        value={fmtPct(avgMdd, 1)}
        className="text-accent-down"
      />
      <SummaryPill
        label="最大 MDD"
        value={fmtPct(maxMdd, 1)}
        className="text-accent-down"
      />
      <SummaryPill
        label="平均波动率"
        value={fmtPct(avgVolatility, 1)}
      />
    </div>
  )
}


function SummaryPill({
  label,
  value,
  className = '',
}: {
  label: string
  value: string
  className?: string
}) {
  return (
    <div className="rounded-md border border-border bg-bg-card px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-ink-faint">
        {label}
      </div>
      <div className={`mt-0.5 font-mono text-xs font-semibold tabular-nums ${className}`}>
        {value}
      </div>
    </div>
  )
}


function average(values: number[]) {
  const finite = values.filter(value => Number.isFinite(value))
  if (finite.length === 0) return 0
  return finite.reduce((sum, value) => sum + value, 0) / finite.length
}


function TodayExecutionWindows({ windows }: { windows: Record<string, ExecutionWindow> }) {
  const rows = Object.values(windows).sort((a, b) => a.ticker.localeCompare(b.ticker))
  if (rows.length === 0) return null

  return (
    <div className="overflow-x-auto border-t border-border px-3 py-2">
      <div className="mb-2 text-[11px] font-medium text-ink-dim">
        当日窗口说明
      </div>
      <table className="w-full min-w-[760px] text-xs">
        <thead className="text-[10px] uppercase tracking-wider text-ink-faint">
          <tr>
            <Th>标的</Th>
            <Th>市场</Th>
            <Th>市场时区</Th>
            <Th>参考交易日</Th>
            <Th>展示时间段</Th>
            <Th right>状态</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.ticker} className="border-t border-border/70">
              <td className="px-4 py-2 font-mono text-ink">{row.ticker}</td>
              <td className="px-4 py-2 text-ink-dim">{row.market}</td>
              <td className="px-4 py-2 font-mono text-ink-dim">{row.market_timezone}</td>
              <td className="px-4 py-2 font-mono text-ink-dim">{row.ref_day}</td>
              <td className="px-4 py-2 font-mono text-ink-dim">
                {row.execution_start && row.execution_end
                  ? `${row.display_timezone} ${formatPlainTime(row.execution_start)} 至 ${formatPlainTime(row.execution_end)}`
                  : '—'}
              </td>
              <td className="px-4 py-2 text-right text-ink-dim">
                {row.market_status === 'open' ? '正在交易' : '已闭市'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}


function ScheduleWarnings({ warnings }: { warnings: BacktestDataWarning[] }) {
  return (
    <div className="grid gap-1 text-[11px] text-ink-dim">
      {warnings.map(w => (
        <div key={`${w.training_start}-${w.training_end}-${w.ticker}-${w.action}`}
             className="flex flex-wrap items-center gap-2">
          <span className={w.action === 'excluded' ? 'text-accent-down' : 'text-ink-dim'}>
            {w.ticker} · {warningLabel(w.action)}
          </span>
          <span className="font-mono text-ink-faint">
            可用 {w.available_start ?? '—'} 至 {w.available_end ?? '—'}
          </span>
          <span className="font-mono text-ink-faint">{w.sample_count} 天</span>
        </div>
      ))}
    </div>
  )
}


function StatusBadge({
  status, refDay,
}: { status: 'open' | 'closed'; refDay: string }) {
  const open = status === 'open'
  return (
    <span
      className={`w-fit rounded border px-1.5 py-0.5 text-[10px]
                  ${open
                    ? 'border-accent-up/40 bg-accent-up/10 text-accent-up'
                    : 'border-border bg-bg-elev text-ink-faint'}`}
      title={`买入参考日：${refDay}`}
    >
      {open ? '正在交易' : '已闭市'} · {refDay}
    </span>
  )
}


function HoldingDetailTable({ rows }: { rows: HoldingDetailRow[] }) {
  return (
    <table className="w-full min-w-[920px] text-xs">
      <thead className="bg-bg-elev/50 text-[10px] uppercase tracking-wider text-ink-faint">
        <tr>
          <Th>标的</Th>
          <Th>购买日期</Th>
          <Th right help={METRIC_EXPLANATIONS.buyPrice}>买入价</Th>
          <Th right help={METRIC_EXPLANATIONS.fxRate}>汇率</Th>
          <Th right help={METRIC_EXPLANATIONS.usdPrice}>美元价</Th>
          <Th right help={METRIC_EXPLANATIONS.sharesBought}>本次股数</Th>
          <Th right help={METRIC_EXPLANATIONS.totalShares}>当时总股数</Th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr className="border-t border-border/70">
            <td colSpan={7} className="px-4 py-6 text-center text-ink-faint">
              暂无成交明细。
            </td>
          </tr>
        ) : rows.map((row, idx) => {
          if (row.kind === 'empty') {
            return (
              <tr key={`${row.ticker}-empty-${idx}`} className="border-t border-border/70">
                <td className="px-4 py-2 font-mono text-ink">{row.ticker}</td>
                <td colSpan={6} className="px-4 py-2 text-ink-faint">
                  {row.reason}
                </td>
              </tr>
            )
          }
          const event = row.event
          return (
            <tr key={`${event.ticker}-${event.purchased_at}-${idx}`}
                className="border-t border-border/70">
              <td className="px-4 py-2 font-mono text-ink">{row.ticker}</td>
              <td className="px-4 py-2 font-mono tabular-nums text-ink-dim">
                {formatPurchaseTime(event)}
              </td>
              <Td right mono>
                {fmtNumber(event.price, event.price > 1000 ? 2 : 4)} {event.currency}
              </Td>
              <Td right mono>
                <div>{fmtNumber(event.fx_rate, event.fx_rate > 100 ? 3 : 5)}</div>
                <div className="text-[10px] font-normal text-ink-faint">
                  {fxSourceLabel(event.fx_source)}
                </div>
                {event.fx_as_of && (
                  <div className="text-[10px] font-normal text-ink-faint">
                    {formatPlainTime(event.fx_as_of)}
                  </div>
                )}
              </Td>
              <Td right mono>{fmtNumber(event.price_usd, 4)}</Td>
              <Td right mono>{fmtNumber(event.shares, 2)}</Td>
              <Td right mono>{fmtNumber(event.total_shares, 2)}</Td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}


function Pager({
  page,
  totalPages,
  onPageChange,
  className = '',
}: {
  page: number
  totalPages: number
  onPageChange: (page: number) => void
  className?: string
}) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const last = Math.max(1, totalPages)
  const current = Math.min(Math.max(1, page), last)

  const go = (target: number) => {
    setError('')
    onPageChange(Math.min(Math.max(1, target), last))
  }

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const next = Number(draft)
    if (!Number.isInteger(next) || next < 1 || next > last) {
      setError(`请输入 1-${last} 的页码`)
      return
    }
    go(next)
    setDraft('')
  }

  return (
    <div className={`flex flex-wrap items-center justify-center gap-2 text-xs ${className}`}>
      <button
        type="button"
        onClick={() => go(1)}
        disabled={current === 1}
        className="h-8 rounded-md border border-border bg-bg-elev px-3 text-ink-dim
                   hover:text-ink disabled:cursor-not-allowed disabled:opacity-45
                   focus:outline-none focus:ring-2 focus:ring-accent"
      >
        首页
      </button>
      <button
        type="button"
        onClick={() => go(current - 1)}
        disabled={current === 1}
        className="h-8 rounded-md border border-border bg-bg-elev px-3 text-ink-dim
                   hover:text-ink disabled:cursor-not-allowed disabled:opacity-45
                   focus:outline-none focus:ring-2 focus:ring-accent"
      >
        上一页
      </button>
      <span className="min-w-[72px] text-center font-mono tabular-nums text-ink-faint">
        {current}/{last}页
      </span>
      <button
        type="button"
        onClick={() => go(current + 1)}
        disabled={current === last}
        className="h-8 rounded-md border border-border bg-bg-elev px-3 text-ink-dim
                   hover:text-ink disabled:cursor-not-allowed disabled:opacity-45
                   focus:outline-none focus:ring-2 focus:ring-accent"
      >
        下一页
      </button>
      <button
        type="button"
        onClick={() => go(last)}
        disabled={current === last}
        className="h-8 rounded-md border border-border bg-bg-elev px-3 text-ink-dim
                   hover:text-ink disabled:cursor-not-allowed disabled:opacity-45
                   focus:outline-none focus:ring-2 focus:ring-accent"
      >
        尾页
      </button>
      <form onSubmit={submit} className="flex items-center gap-2">
        <input
          type="number"
          min={1}
          max={last}
          value={draft}
          onChange={event => {
            setDraft(event.target.value)
            setError('')
          }}
          placeholder="页码"
          aria-label="跳转页码"
          className="h-8 w-20 rounded-md border border-border bg-bg-elev px-2
                     font-mono text-xs text-ink focus:outline-none
                     focus:ring-2 focus:ring-accent"
        />
        {error && <span className="text-accent-down">{error}</span>}
      </form>
    </div>
  )
}


function costBasisForEvents(events: BacktestPurchaseEvent[]): HoldingCostBasis | null {
  let localCost = 0
  let usdCost = 0
  let shares = 0
  for (const event of events) {
    if (event.shares <= 0) continue
    localCost += event.price * event.shares
    usdCost += event.price_usd * event.shares
    shares += event.shares
  }
  return shares > 0
    ? { avgLocal: localCost / shares, avgUsd: usdCost / shares, shares }
    : null
}


function buildHoldingDetailRows(
  holdings: Holding[],
  eventsByTicker: Map<string, BacktestPurchaseEvent[]>,
  filter: string,
  planAmount: number,
): HoldingDetailRow[] {
  const selected = filter === ALL_HOLDINGS
    ? holdings
    : holdings.filter(h => h.ticker === filter)
  return selected.flatMap<HoldingDetailRow>(holding => {
    const events = (eventsByTicker.get(holding.ticker) ?? [])
      .slice()
      .sort((a, b) => new Date(a.purchased_at).getTime() - new Date(b.purchased_at).getTime())
    if (events.length > 0) {
      return events.map<HoldingDetailRow>(event => ({
        kind: 'event',
        ticker: holding.ticker,
        event,
      }))
    }
    return [{
      kind: 'empty',
      ticker: holding.ticker,
      reason: noPurchaseReason(holding, planAmount),
    }]
  })
}


function noPurchaseReason(holding: Holding, planAmount: number): string {
  const base = '本区间无实际成交，可能因权重预算不足一手或训练窗口未分配权重。'
  if (holding.last_price_usd == null) return base
  const lotCost = holding.last_price_usd * lotSizeForSymbol(holding.ticker)
  const budget = planAmount * holding.weight
  return `${base} 参考一手约 ${fmtNumber(lotCost, 2)} USD，单次目标预算约 ${fmtNumber(budget, 2)} USD。`
}


function lotSizeForSymbol(symbol: string): number {
  const suffix = symbol.split('.').pop()?.toUpperCase()
  return suffix && ['SH', 'SS', 'SZ', 'HK'].includes(suffix) ? 100 : 1
}


function DataWarningsNotice({ warnings }: { warnings: BacktestDataWarning[] }) {
  if (warnings.length === 0) return null
  const excluded = warnings.filter(w => w.action === 'excluded')
  const partial = warnings.filter(w => w.action === 'annualized_short_history')
  const title = warnings
    .map(w => `${w.training_start} 至 ${w.training_end} ${w.ticker}: ${w.sample_count} 天，${warningLabel(w.action)}`)
    .join('\n')

  return (
    <div className="flex flex-wrap items-center gap-1" title={title}>
      {excluded.length > 0 && (
        <span className="rounded border border-accent-down/40 bg-accent-down/10
                         px-1.5 py-0.5 text-[10px] font-medium text-accent-down">
          短历史剔除 {excluded.length}
        </span>
      )}
      {partial.length > 0 && (
        <span className="rounded border border-border bg-bg-elev/60
                         px-1.5 py-0.5 text-[10px] font-medium text-ink-dim">
          部分年化 {partial.length}
        </span>
      )}
    </div>
  )
}


function warningLabel(action: BacktestDataWarning['action']) {
  return action === 'excluded' ? '已从该窗口权重剔除' : '按可用数据年化'
}


function formatPurchaseTime(event: BacktestPurchaseEvent): string {
  return `${formatPlainTime(event.purchased_at)} ${event.purchased_at_timezone ?? event.timezone}`
}


function formatPlainTime(value: string): string {
  return value.includes('T') ? value.replace('T', ' ').slice(0, 16) : value
}


function fxSourceLabel(source: BacktestPurchaseEvent['fx_source']): string {
  if (source === 'minute_asof') return '分钟对齐'
  if (source === 'hourly_approx') return '小时近似'
  if (source === 'base_currency') return '基准货币'
  return '日线近似'
}


function Metric({
  label, value, colorClass = '', help,
}: { label: string; value: string; colorClass?: string; help?: string }) {
  return (
    <div className="rounded-md border border-border bg-bg-elev/40 px-3 py-2">
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-ink-faint">
        {label}
        {help && <InfoTooltip content={help} />}
      </div>
      <div className={`mt-0.5 font-mono text-base font-semibold tabular-nums ${colorClass}`}>
        {value}
      </div>
    </div>
  )
}


function Th({
  children, right, title, help,
}: { children: React.ReactNode; right?: boolean; title?: string; help?: string }) {
  return (
    <th
      title={title}
      className={`px-4 py-2 ${right ? 'text-right' : 'text-left'} font-medium`}
    >
      <span className={`inline-flex items-center gap-1 ${right ? 'justify-end' : 'justify-start'}`}>
        {children}
        {help && <InfoTooltip content={help} />}
      </span>
    </th>
  )
}


function Td({
  children, right, mono, className = '',
}: { children: React.ReactNode; right?: boolean; mono?: boolean; className?: string }) {
  return (
    <td className={`px-4 py-2 ${right ? 'text-right' : 'text-left'}
                    ${mono ? 'font-mono tabular-nums' : ''} ${className}`}>
      {children}
    </td>
  )
}


function indicatorLabel(name: string): string {
  switch (name) {
    case 'annualized_roi': return '年化'
    case 'dividend_yield': return '股息'
    case 'max_drawdown': return 'MDD'
    case 'drawdown_duration': return '回撤'
    case 'recovery_time': return '恢复'
    case 'volatility': return '波动'
    case 'beta': return 'Beta'
    default: return name
  }
}


function rfSourceLabel(s: 'bil_default' | 'override' | 'constant_fallback'): string {
  switch (s) {
    case 'bil_default':       return 'BIL.US 前365天年化收益（默认）'
    case 'override':          return '用户手动指定'
    case 'constant_fallback': return 'BIL 不可用，回落至 3% 常数'
  }
}
