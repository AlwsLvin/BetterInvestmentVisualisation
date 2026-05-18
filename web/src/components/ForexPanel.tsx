import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { IntradaySeries } from '@/api/types'
import { MiniIntradayChart } from './MiniIntradayChart'
import { useView } from '@/stores/view'
import { fmtSignedPct, trendColor } from '@/utils/format'
import {
  FX_PAIRS,
  type ForexDisplay,
  type ForexPair,
  forexDisplay,
  intradayDelta,
  invertIntradaySeries,
} from '@/utils/forex'

export function ForexPanel() {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-dim">
            外汇 · 实时汇率
          </div>
          <h2 className="text-xl font-semibold sm:text-2xl">主要货币对</h2>
        </div>
        <span className="text-xs text-ink-faint">60 秒刷新</span>
      </header>

      <div className="min-h-0 flex-1 overflow-auto pr-1">
        <div className="grid gap-2">
          {FX_PAIRS.map(pair => (
            <ForexPairCards key={pair.symbol} pair={pair} />
          ))}
        </div>
      </div>
    </div>
  )
}

function ForexPairCards({ pair }: { pair: ForexPair }) {
  const goFx = useView(s => s.goFx)
  const query = useQuery({
    queryKey: ['fx-intraday', pair.symbol],
    queryFn: () => api.fxIntraday(pair.symbol),
    staleTime: 60 * 1000,
    refetchInterval: 60 * 1000,
  })

  const inverse = useMemo(
    () => query.data ? invertIntradaySeries(query.data, pair) : undefined,
    [query.data, pair],
  )

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <ForexRateCard
        display={forexDisplay(pair, false)}
        series={query.data}
        isLoading={query.isLoading}
        error={query.isError ? (query.error as Error).message : undefined}
        onClick={() => goFx(pair.symbol, false)}
      />
      <ForexRateCard
        display={forexDisplay(pair, true)}
        series={inverse}
        isLoading={query.isLoading}
        error={query.isError ? (query.error as Error).message : undefined}
        onClick={() => goFx(pair.symbol, true)}
      />
    </div>
  )
}

function ForexRateCard({
  display,
  series,
  isLoading,
  error,
  onClick,
}: {
  display: ForexDisplay
  series?: IntradaySeries
  isLoading: boolean
  error?: string
  onClick: () => void
}) {
  const delta = series ? intradayDelta(series) : null
  const deltaClass = delta == null ? 'text-ink-faint' : trendColor(delta)

  return (
    <button
      type="button"
      onClick={onClick}
      className="grid min-h-[76px] grid-cols-[minmax(88px,128px)_minmax(120px,1fr)_minmax(64px,82px)]
                 items-center gap-3 rounded-lg border border-border bg-bg-elev/45
                 px-3 py-2 text-left transition-colors hover:bg-bg-elev
                 focus:outline-none focus:ring-2 focus:ring-accent"
    >
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-ink" title={display.name}>
          {display.name}
        </div>
        <div className="mt-0.5 font-mono text-[11px] text-ink-faint">
          {display.code}
          {series?.display_timezone ? ` · ${series.display_timezone}` : ''}
        </div>
      </div>

      <div className="h-[52px] min-w-0">
        {series && series.points.length >= 2 ? (
          <MiniIntradayChart series={series} trendValue={delta} />
        ) : (
          <div className="grid h-full place-items-center text-xs text-ink-faint">
            {error ? '加载失败' : isLoading ? '加载中…' : '暂无数据'}
          </div>
        )}
      </div>

      <div
        className={`text-right font-mono text-sm font-semibold tabular-nums ${deltaClass}`}
        title={error}
      >
        {delta == null ? '—' : fmtSignedPct(delta)}
      </div>
    </button>
  )
}
