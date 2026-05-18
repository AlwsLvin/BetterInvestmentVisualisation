import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '@/api/client'
import type {
  AssetDetailRangeKey,
  AssetInfo,
  AssetKlinePeriod,
  BacktestPurchaseEvent,
  RangeKey,
} from '@/api/types'
import { AssetChart, type ChartType } from '@/components/AssetChart'
import { InfoTooltip } from '@/components/InfoTooltip'
import { SearchOverlay } from '@/components/SearchOverlay'
import { SEARCH_LAYOUT_ID } from '@/components/SearchBar'
import { useView } from '@/stores/view'
import { useWatchlist, DEFAULT_WATCHLIST_ID } from '@/stores/watchlist'
import { fmtSignedPct, fmtNumber, trendColor, fmtPct } from '@/utils/format'
import { isIndexSymbol, toProjectSymbol } from '@/utils/symbols'
import { METRIC_EXPLANATIONS } from '@/utils/metricExplanations'

const INDEX_RANGES: RangeKey[] = ['today', '7d', '30d', '90d', 'ytd', '1y', '3y', '5y']
const ASSET_RANGES: AssetDetailRangeKey[] = ['today', '7d', 'dayK', 'quarterK', 'yearK']
const RANGE_LABEL: Record<RangeKey, string> = {
  today: '当日', '7d': '7天', '30d': '30天', '90d': '90天',
  ytd: '年初至今',
  '1y': '1年', '3y': '3年', '5y': '5年',
}
const ASSET_RANGE_LABEL: Record<AssetDetailRangeKey, string> = {
  ...RANGE_LABEL,
  dayK: '日K',
  quarterK: '季K',
  yearK: '年K',
}
const RANGE_TITLE: Partial<Record<RangeKey, string>> = {
  ytd: `当年至今 (YTD)：${new Date().getFullYear()}-01-01 至今`,
  '1y': '回溯 1 年：一年前至今',
}
const ASSET_RANGE_TITLE: Partial<Record<AssetDetailRangeKey, string>> = {
  today: '当日1分钟分时曲线',
  '7d': '最近7日曲线',
  dayK: '全部可用历史的每日K线',
  quarterK: '全部可用历史按自然季度聚合',
  yearK: '全部可用历史按自然年聚合',
}

function isKRange(range: AssetDetailRangeKey): range is 'dayK' | 'quarterK' | 'yearK' {
  return range === 'dayK' || range === 'quarterK' || range === 'yearK'
}

function klinePeriod(range: 'dayK' | 'quarterK' | 'yearK'): AssetKlinePeriod {
  if (range === 'quarterK') return 'quarter'
  if (range === 'yearK') return 'year'
  return 'day'
}

interface Props {
  symbol: string
}

export function AssetDetail({ symbol }: Props) {
  const goBack = useView(s => s.goBack)
  const costRange = useView(s => {
    if (s.view.type === 'asset' && s.view.returnTo?.type === 'portfolio') {
      return s.view.returnTo.range
    }
    return s.homeRange
  })
  const ids = useWatchlist(s => s.order)
  const watchlists = useWatchlist(s => s.watchlists)
  const activeId = useWatchlist(s => s.activeId || DEFAULT_WATCHLIST_ID)
  const activeWatchlist = useWatchlist(s => s.watchlists[s.activeId] ?? s.watchlists[DEFAULT_WATCHLIST_ID])
  const plan = useWatchlist(s => s.plans[s.activeId] ?? s.plans[DEFAULT_WATCHLIST_ID])
  const prefs = useWatchlist(s => s.prefs[s.activeId] ?? s.prefs[DEFAULT_WATCHLIST_ID])
  const addTicker = useWatchlist(s => s.addTicker)
  const isIndex = isIndexSymbol(symbol)
  const [range, setRange] = useState<AssetDetailRangeKey>(isIndex ? '1y' : 'dayK')
  const [searchOpen, setSearchOpen] = useState(false)
  const [addChooserOpen, setAddChooserOpen] = useState(false)

  const projectSymbol = toProjectSymbol(symbol)
  const allAdded = ids.length > 0 && ids.every(id => watchlists[id]?.tickers.includes(projectSymbol))
  const inActiveWatchlist = !isIndex && !!activeWatchlist?.tickers.includes(projectSymbol)
  const chartType: ChartType = isKRange(range) ? 'candle' : 'line'
  const visibleRanges = isIndex ? INDEX_RANGES : ASSET_RANGES

  const settingsQ = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.getSettings(),
    enabled: inActiveWatchlist,
    staleTime: 0,
  })
  const allocationLookbackDays = settingsQ.data?.allocation_lookback_days ?? 365

  const costQ = useQuery({
    queryKey: ['rolling-backtest', activeId, activeWatchlist?.tickers ?? [],
               prefs.style, prefs.scheme, prefs.tau, prefs.power, prefs.floor,
               plan.amount, plan.frequency, costRange, allocationLookbackDays],
    queryFn: () => api.rollingBacktest({
      tickers: activeWatchlist!.tickers,
      style: prefs.style,
      scheme: prefs.scheme,
      tau: prefs.tau,
      power: prefs.power,
      floor: prefs.floor,
      plan: { amount: plan.amount, frequency: plan.frequency },
      range: costRange,
    }),
    enabled: inActiveWatchlist && !!activeWatchlist && activeWatchlist.tickers.length > 0,
    refetchInterval: costRange === 'today' ? 60 * 1000 : false,
  })

  const seriesQ = useQuery({
    queryKey: [isIndex ? 'index' : 'asset', symbol, range],
    queryFn: () => {
      if (!isIndex && isKRange(range)) {
        return api.assetKline(symbol, klinePeriod(range))
      }
      const apiRange = range as RangeKey
      return isIndex
        ? api.index(symbol, apiRange)
        : api.asset(symbol, apiRange, true, apiRange === '7d')
    },
    refetchInterval: range === 'today' ? 60 * 1000 : false,
  })

  const infoQ = useQuery({
    queryKey: ['asset-info', symbol],
    queryFn: () => api.assetInfo(symbol),
    enabled: !isIndex,
    staleTime: 60 * 60 * 1000,
    refetchInterval: range === 'today' ? 60 * 1000 : false,
  })

  const data = seriesQ.data
  const intradayLast = data?.points[data.points.length - 1]?.close ?? 0
  const last = data?.quote?.last_price ?? intradayLast
  const firstPoint = data?.points[0]
  const first = firstPoint ? (firstPoint.open && firstPoint.open > 0 ? firstPoint.open : firstPoint.close) : 0
  const delta = data?.quote?.change_pct ?? (first > 0 ? (intradayLast - first) / first : 0)
  const averageCost = inActiveWatchlist
    ? averageCostForTicker(costQ.data?.purchase_events ?? [], projectSymbol)
    : null

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="grid min-h-screen min-h-dvh w-full grid-rows-[auto_minmax(0,1fr)]
                 gap-3 p-3 safe-area-top safe-area-bottom
                 lg:h-screen lg:gap-4 lg:p-4"
    >
      <header className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={goBack}
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
          <div className="hidden text-xs uppercase tracking-wider text-ink-dim sm:block">
            {isIndex ? '指数' : '资产'}
          </div>
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
            <h1 className="max-w-[9rem] truncate font-mono text-lg font-semibold sm:max-w-none sm:text-2xl">
              {symbol}
            </h1>
            {infoQ.data?.name && (
              <span className="hidden truncate text-sm text-ink-dim sm:inline">
                {infoQ.data.name}
              </span>
            )}
            {data && (
              <>
                <span className="font-mono text-sm tabular-nums sm:text-xl">
                  {fmtNumber(last, 2)}
                </span>
                <span className={`font-mono text-xs tabular-nums sm:text-sm ${trendColor(delta)}`}>
                  {fmtSignedPct(delta)}
                </span>
                {range === 'today' && data.market_status && data.ref_day && (
                  <MarketStatusBadge status={data.market_status} refDay={data.ref_day} />
                )}
              </>
            )}
          </div>
        </div>

        <div className="ml-auto w-full sm:w-[320px] lg:w-[360px]">
          <AnimatePresence initial={false}>
            {!searchOpen && (
              <motion.div
                key="asset-searchbar-idle"
                layoutId={SEARCH_LAYOUT_ID}
                className="relative h-tap w-full"
                transition={{ type: 'spring', stiffness: 300, damping: 32 }}
              >
                <button
                  type="button"
                  onClick={() => setSearchOpen(true)}
                  aria-label="打开搜索"
                  className="flex h-full min-h-tap w-full items-center gap-2
                             rounded-lg border border-border bg-bg-card py-2
                             pl-9 pr-3 text-left text-sm text-ink-faint
                             hover:bg-bg-elev hover:text-ink-dim
                             focus:outline-none focus:ring-2 focus:ring-accent"
                >
                  搜索股票 / ETF / 指数
                </button>
                <svg
                  className="pointer-events-none absolute left-3 top-1/2
                             h-4 w-4 -translate-y-1/2 text-ink-faint"
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                  <circle cx="11" cy="11" r="7" />
                  <path d="m20 20-3.5-3.5" />
                </svg>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </header>

      <div className="flex h-full flex-col gap-3 rounded-xl border border-border
                      bg-bg-card p-4 overflow-hidden">
        <StatsBar info={infoQ.data} fallback={fallbackStatsFromSeries(data)} />

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-1 overflow-x-auto scrollbar-hide">
            {visibleRanges.map(r => {
              const active = r === range
              return (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  title={isIndex ? RANGE_TITLE[r as RangeKey] : ASSET_RANGE_TITLE[r]}
                  className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium
                              transition-colors min-h-[32px]
                              ${active
                                ? 'bg-accent text-white'
                                : 'text-ink-dim hover:bg-bg-elev hover:text-ink'}`}
                >
                  {isIndex ? RANGE_LABEL[r as RangeKey] : ASSET_RANGE_LABEL[r]}
                </button>
              )
            })}
          </div>

          <div className="flex items-center gap-2">
            {!isIndex && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => !allAdded && setAddChooserOpen(v => !v)}
                  disabled={allAdded}
                  className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white
                             min-h-[32px] disabled:opacity-50 disabled:cursor-not-allowed
                             hover:brightness-110 focus:outline-none focus:ring-2
                             focus:ring-accent"
                >
                  {allAdded ? '已添加' : '添加'}
                </button>
                <AnimatePresence>
                  {addChooserOpen && !allAdded && (
                    <AddToPortfolioChooser
                      symbol={projectSymbol}
                      ids={ids}
                      watchlists={watchlists}
                      onChoose={id => {
                        addTicker(id, projectSymbol)
                        setAddChooserOpen(false)
                      }}
                    />
                  )}
                </AnimatePresence>
              </div>
            )}
          </div>
        </div>

        <div className="flex-1 min-h-[260px]">
          {seriesQ.isLoading && (
            <div className="grid h-full place-items-center text-ink-faint text-sm">
              加载中…
            </div>
          )}
          {seriesQ.isError && (
            <div className="grid h-full place-items-center text-accent-down text-sm">
              加载失败：{(seriesQ.error as Error).message}
            </div>
          )}
          {data && (
            <AssetChart
              series={data}
              type={chartType}
              latestPrice={last}
              averageCost={averageCost}
              trendValue={range === 'today' || range === '7d' ? delta : null}
            />
          )}
        </div>
      </div>

      <AnimatePresence>
        {searchOpen && (
          <SearchOverlay key="search-overlay"
                         onClose={() => setSearchOpen(false)} />
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function averageCostForTicker(events: BacktestPurchaseEvent[], ticker: string) {
  let cost = 0
  let shares = 0
  for (const event of events) {
    if (event.ticker !== ticker || event.shares <= 0) continue
    cost += event.price * event.shares
    shares += event.shares
  }
  return shares > 0 ? cost / shares : null
}


function AddToPortfolioChooser({
  symbol,
  ids,
  watchlists,
  onChoose,
}: {
  symbol: string
  ids: string[]
  watchlists: ReturnType<typeof useWatchlist.getState>['watchlists']
  onChoose: (id: string) => void
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.12 }}
      className="absolute right-0 top-[calc(100%+8px)] z-20 w-64 rounded-lg
                 border border-border bg-bg-card p-2 shadow-xl shadow-black/30"
    >
      <div className="mb-2 text-[11px] uppercase tracking-wider text-ink-faint">
        添加到组合
      </div>
      <div className="grid gap-1.5">
        {ids.map(id => {
          const w = watchlists[id]
          if (!w) return null
          const exists = w.tickers.includes(symbol)
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChoose(id)}
              disabled={exists}
              className="flex min-h-[34px] items-center justify-between gap-2
                         rounded-md border border-border bg-bg-elev/50 px-2
                         text-left text-xs text-ink-dim hover:text-ink
                         disabled:cursor-not-allowed disabled:opacity-45
                         focus:outline-none focus:ring-2 focus:ring-accent"
            >
              <span className="truncate">{w.name}</span>
              <span className="font-mono text-[11px] text-ink-faint">
                {exists ? '已添加' : `${w.tickers.length}`}
              </span>
            </button>
          )
        })}
      </div>
    </motion.div>
  )
}


function MarketStatusBadge({
  status, refDay,
}: { status: 'open' | 'closed'; refDay: string }) {
  const open = status === 'open'
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-[10px]
                  ${open
                    ? 'border-accent-up/40 bg-accent-up/10 text-accent-up'
                    : 'border-border bg-bg-elev text-ink-faint'}`}
      title={`买入参考日：${refDay}`}
    >
      {open ? '正在交易' : '已闭市'} · {refDay}
    </span>
  )
}


function StatsBar({
  info, fallback,
}: {
  info?: AssetInfo
  fallback: {
    week52_high: number | null
    week52_low: number | null
    open: number | null
    day_high: number | null
    day_low: number | null
    previous_close: number | null
  }
}) {
  const [expanded, setExpanded] = useState(false)
  const renderPrice = (n: number) => fmtNumber(n, n > 1000 ? 0 : 2)
  const items: { label: string; value: string; help: string }[] = [
    {
      label: '52周新高',
      value: fmt(info?.week52_high ?? fallback.week52_high, renderPrice),
      help: METRIC_EXPLANATIONS.week52High,
    },
    {
      label: '52周新低',
      value: fmt(info?.week52_low ?? fallback.week52_low, renderPrice),
      help: METRIC_EXPLANATIONS.week52Low,
    },
    {
      label: 'PE (TTM)',
      value: fmt(info?.pe_ratio, n => n.toFixed(2)),
      help: METRIC_EXPLANATIONS.peRatio,
    },
    {
      label: '股息率',
      value: fmt(info?.dividend_yield, n => fmtPct(n, 2)),
      help: METRIC_EXPLANATIONS.dividendYield,
    },
    { label: '市值', value: fmt(info?.market_cap, fmtCompact), help: METRIC_EXPLANATIONS.marketCap },
    { label: '成交量', value: fmt(info?.volume, fmtCompact), help: METRIC_EXPLANATIONS.volume },
  ]
  const extra: { label: string; value: string; help: string }[] = [
    {
      label: '开盘价',
      value: fmt(info?.open ?? fallback.open, renderPrice),
      help: METRIC_EXPLANATIONS.openPrice,
    },
    {
      label: '当日最高',
      value: fmt(info?.day_high ?? fallback.day_high, renderPrice),
      help: METRIC_EXPLANATIONS.dayHigh,
    },
    {
      label: '当日最低',
      value: fmt(info?.day_low ?? fallback.day_low, renderPrice),
      help: METRIC_EXPLANATIONS.dayLow,
    },
    {
      label: '前收盘',
      value: fmt(info?.previous_close ?? fallback.previous_close, renderPrice),
      help: METRIC_EXPLANATIONS.previousClose,
    },
  ]
  const visibleItems = expanded
    ? [...items, ...extra]
    : items.map((item, index) => ({ ...item, mobileHidden: index >= 4 }))
  return (
    <div className="relative z-10">
      <div className="grid grid-cols-[minmax(0,1fr)_48px] gap-2">
        <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-6">
          {visibleItems.map(item => (
            <StatCell
              key={item.label}
              item={item}
              className={'mobileHidden' in item && item.mobileHidden ? 'hidden sm:block' : ''}
            />
          ))}
        </div>
        <button
          type="button"
          title={expanded ? '收起' : '展开更多指标'}
          aria-label={expanded ? '收起' : '展开更多指标'}
          onClick={() => setExpanded(v => !v)}
          className="grid min-w-[48px] shrink-0 place-items-center rounded-md border border-border
                     bg-bg-elev px-3 py-2 text-ink-dim hover:text-ink
                     focus:outline-none focus:ring-2 focus:ring-accent"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" strokeWidth={2}>
            {expanded ? <path d="m6 15 6-6 6 6" /> : <path d="m6 9 6 6 6-6" />}
          </svg>
        </button>
      </div>
    </div>
  )
}


function StatCell({
  item,
  className = '',
}: {
  item: { label: string; value: string; help: string }
  className?: string
}) {
  return (
    <div className={`min-w-0 rounded-md border border-border bg-bg-elev px-3 py-2 ${className}`}>
      <div className="flex min-w-0 items-center gap-1 text-[10px] uppercase tracking-wider text-ink-faint">
        <span className="truncate">{item.label}</span>
        <InfoTooltip content={item.help} />
      </div>
      <div className="mt-0.5 truncate font-mono text-sm font-semibold tabular-nums">
        {item.value}
      </div>
    </div>
  )
}


function fallbackStatsFromSeries(s: import('@/api/types').AssetSeries | undefined) {
  const empty = {
    week52_high: null,
    week52_low: null,
    open: null,
    day_high: null,
    day_low: null,
    previous_close: null,
  }
  if (!s || s.points.length === 0) return empty
  const closes = s.points.map(p => p.close)
  const first = s.points[0]
  return {
    week52_high: Math.max(...closes),
    week52_low: Math.min(...closes),
    open: first.open ?? first.close,
    day_high: Math.max(...closes),
    day_low: Math.min(...closes),
    previous_close: s.points.length >= 2 ? s.points[s.points.length - 2].close : null,
  }
}


function fmt(n: number | null | undefined, render: (n: number) => string): string {
  if (n == null || isNaN(n) || !isFinite(n)) return '—'
  return render(n)
}


function fmtCompact(n: number): string {
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9)  return `${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6)  return `${(n / 1e6).toFixed(2)}M`
  if (n >= 1e3)  return `${(n / 1e3).toFixed(1)}K`
  return n.toFixed(0)
}
