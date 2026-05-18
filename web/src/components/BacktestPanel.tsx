import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '@/api/client'
import type { BacktestDataWarning, RangeKey } from '@/api/types'
import { useView } from '@/stores/view'
import { useWatchlist, DEFAULT_WATCHLIST_ID } from '@/stores/watchlist'
import { fmtSignedPct, fmtPct, trendColor } from '@/utils/format'
import { PortfolioControls } from './PortfolioControls'
import { AllocationBars } from './AllocationBars'
import { BacktestChart } from './BacktestChart'
import { BenchmarkPicker } from './BenchmarkPicker'
import { PortfolioEditor } from './PortfolioEditor'
import { InfoTooltip } from './InfoTooltip'
import { holdingReturnSeries, returnSeriesFromPoints } from '@/utils/performance'
import { isIndexSymbol } from '@/utils/symbols'
import { benchmarkDetailTitle } from '@/utils/benchmark'
import { METRIC_EXPLANATIONS, withContext } from '@/utils/metricExplanations'

interface Props {
  range: RangeKey
  onSearch?: (targetWatchlistId?: string) => void
}

export function BacktestPanel({ range, onSearch }: Props) {
  const [editorOpen, setEditorOpen] = useState(false)
  const [benchmarkSymbol, setBenchmarkSymbol] = useState<string | undefined>()
  const goPortfolio = useView(s => s.goPortfolio)
  const activeId = useWatchlist(s => s.activeId || DEFAULT_WATCHLIST_ID)
  const watchlist = useWatchlist(s => s.watchlists[s.activeId] ?? s.watchlists[DEFAULT_WATCHLIST_ID])
  const plan = useWatchlist(s => s.plans[s.activeId] ?? s.plans[DEFAULT_WATCHLIST_ID])
  const prefs = useWatchlist(s => s.prefs[s.activeId] ?? s.prefs[DEFAULT_WATCHLIST_ID])
  const setPlan = useWatchlist(s => s.setPlan)
  const setPrefs = useWatchlist(s => s.setPrefs)
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
      style: prefs.style,
      scheme: prefs.scheme,
      tau: prefs.tau,
      power: prefs.power,
      floor: prefs.floor,
      plan: { amount: plan.amount, frequency: plan.frequency },
      range,
    }),
    enabled: watchlist.tickers.length > 0,
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

  const benchmark = benchmarkSymbol && benchmarkQ.data
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

  const ret = backtestQ.data?.cumulative_return ?? 0
  const ann = backtestQ.data?.annualized_return ?? null
  const mdd = backtestQ.data?.max_drawdown ?? 0
  const currentAllocation = backtestQ.data?.allocation_schedule.at(-1)?.allocation
  const currentTraining = backtestQ.data?.allocation_schedule.at(-1)
  const dataWarnings = backtestQ.data?.data_warnings ?? []

  return (
    <div className="flex h-full min-w-0 flex-col gap-3 overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wider text-ink-dim">
              自选组合 · 回测
            </div>
            <div className="flex items-baseline gap-2">
              <h2 className="truncate text-xl font-semibold sm:text-2xl">
                {watchlist.name}
              </h2>
              <span className="text-xs text-ink-faint">
                {watchlist.tickers.length} 个标的
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => goPortfolio(range, benchmarkSymbol)}
            className="self-stretch rounded-md border border-accent bg-accent/10
                       px-4 text-sm font-medium text-accent hover:bg-accent/20
                       focus:outline-none focus:ring-2 focus:ring-accent"
          >
            详情 →
          </button>
        </div>
        <button
          type="button"
          onClick={() => setEditorOpen(o => !o)}
          className="rounded-md border border-border bg-bg-elev px-3 py-1.5
                     text-xs text-ink-dim hover:text-ink min-h-[32px]
                     focus:outline-none focus:ring-2 focus:ring-accent"
        >
          {editorOpen ? '完成' : '编辑标的'}
        </button>
      </header>

      <AnimatePresence initial={false} mode="wait">
        {editorOpen ? (
          <motion.section
            key="portfolio-list"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
            className="min-h-0 flex-1 overflow-auto rounded-lg border border-border
                       bg-bg-elev/30 p-3"
          >
            <PortfolioEditor onSearch={onSearch} />
          </motion.section>
        ) : (
          <motion.div
            key="backtest"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
            className="flex min-h-0 min-w-0 flex-1 flex-col gap-3"
          >
            <PortfolioControls
              prefs={prefs}
              plan={plan}
              onPrefs={p => setPrefs(activeId, p)}
              onPlan={p => setPlan(activeId, p)}
            />

            {backtestQ.isError && (
              <ErrorBox label="滚动分配 / 回测失败" detail={(backtestQ.error as Error).message} />
            )}

            <div className="grid min-h-0 min-w-0 flex-1 gap-3
                            xl:grid-cols-[minmax(220px,1fr)_minmax(0,2fr)] xl:items-stretch">
              <section className="rounded-lg border border-border bg-bg-elev/30 p-3
                                  flex min-w-0 flex-col gap-2 min-h-[160px]">
                <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-2">
                  <span className="inline-flex items-center gap-1 text-[11px] uppercase
                                   tracking-wider text-ink-faint">
                    投资比例
                    <InfoTooltip content={METRIC_EXPLANATIONS.weight} />
                  </span>
                  {backtestQ.isLoading && (
                    <span className="text-[11px] text-ink-faint">计算中…</span>
                  )}
                  {currentTraining && (
                    <span className="text-[11px] text-ink-faint">
                      执行：{currentTraining.effective_start} 至 {currentTraining.effective_end}
                      {' · '}
                      训练：{currentTraining.training_start} 至 {currentTraining.training_end}
                    </span>
                  )}
                </div>
                {currentAllocation ? (
                  <AllocationBars
                    allocation={currentAllocation}
                    className="overflow-y-auto"
                  />
                ) : (
                  <div className="flex-1 grid place-items-center text-ink-faint text-xs">
                    {watchlist.tickers.length === 0 ? '请先添加标的' : '加载中…'}
                  </div>
                )}
              </section>

              <section className="rounded-lg border border-border bg-bg-elev/30 p-3
                                  flex min-w-0 flex-col gap-2 min-h-[260px]">
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="text-[11px] uppercase tracking-wider text-ink-faint">
                      {range} 回测曲线（标点 = 买入日）
                    </span>
                    <DataWarningsNotice warnings={dataWarnings} />
                  </div>
                  {backtestQ.data && (
                    <div className="flex min-w-0 flex-wrap gap-3 font-mono text-xs tabular-nums">
                      <Stat
                        label="累计"
                        value={fmtSignedPct(ret)}
                        colorClass={trendColor(ret)}
                        help={METRIC_EXPLANATIONS.dcaLatest}
                      />
                      <Stat
                        label="资金年化"
                        value={ann == null ? '—' : fmtSignedPct(ann)}
                        colorClass={ann == null ? 'text-ink-faint' : trendColor(ann)}
                        help={METRIC_EXPLANATIONS.dcaAnnualized}
                      />
                      <Stat
                        label="MDD"
                        value={fmtPct(mdd)}
                        colorClass="text-accent-down"
                        help={METRIC_EXPLANATIONS.maxDrawdown}
                      />
                      {activeBenchmark && (
                        <>
                          <Stat
                            label="基准"
                            value={fmtSignedPct(activeBenchmark.cumulativeReturn)}
                            colorClass={trendColor(activeBenchmark.cumulativeReturn)}
                            help={withContext(METRIC_EXPLANATIONS.benchmarkReturn, activeBenchmarkTitle)}
                          />
                          <Stat
                            label="基准MDD"
                            value={fmtPct(activeBenchmark.maxDrawdown)}
                            colorClass="text-accent-down"
                            help={withContext(METRIC_EXPLANATIONS.benchmarkMaxDrawdown, activeBenchmarkTitle)}
                          />
                        </>
                      )}
                    </div>
                  )}
                </div>
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <BenchmarkPicker
                    value={benchmarkSymbol}
                    onSelect={setBenchmarkSymbol}
                    onClear={() => setBenchmarkSymbol(undefined)}
                  />
                  {benchmarkQ.isError && (
                    <span className="text-xs text-accent-down">
                      基准加载失败：{(benchmarkQ.error as Error).message}
                    </span>
                  )}
                </div>
                <div className="relative min-h-[220px] min-w-0 flex-1">
                  {backtestQ.isError ? (
                    <ErrorBox label="回测失败" detail={(backtestQ.error as Error).message} />
                  ) : backtestQ.data ? (
                    <BacktestChart
                      data={backtestQ.data}
                      benchmark={activeBenchmark
                        ? { label: '基准', data: activeBenchmark }
                        : null}
                    />
                  ) : (
                    <div className="absolute inset-0 grid place-items-center text-ink-faint text-xs">
                      {watchlist.tickers.length === 0 ? '请先添加标的' : '回测计算中…'}
                    </div>
                  )}
                </div>
              </section>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}


function Stat({ label, value, colorClass, help }:
  { label: string; value: string; colorClass: string; help?: string }) {
  return (
    <span>
      <span className="inline-flex items-center gap-1 text-ink-faint">
        {label}
        {help && <InfoTooltip content={help} />}
      </span>{' '}
      <span className={colorClass}>{value}</span>
    </span>
  )
}

function ErrorBox({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="rounded-md border border-accent-down/40 bg-accent-down/10 p-3
                    text-xs text-accent-down">
      <div className="font-medium">{label}</div>
      <div className="mt-1 text-accent-down/80">{detail}</div>
    </div>
  )
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
        <span className="rounded border border-border bg-bg-card
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
