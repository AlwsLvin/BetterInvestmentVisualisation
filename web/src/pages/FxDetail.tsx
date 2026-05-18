import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '@/api/client'
import type { AssetDetailRangeKey, AssetKlinePeriod, RangeKey } from '@/api/types'
import { AssetChart, type ChartType } from '@/components/AssetChart'
import { useView } from '@/stores/view'
import { fmtNumber, fmtSignedPct, trendColor } from '@/utils/format'
import {
  findForexPair,
  forexDisplay,
  formatQuoteTime,
  intradayDelta,
  invertAssetSeries,
  latestRate,
  quoteSourceText,
} from '@/utils/forex'

const FX_RANGES: AssetDetailRangeKey[] = ['today', '7d', 'dayK', 'quarterK', 'yearK']
const FX_RANGE_LABEL: Record<AssetDetailRangeKey, string> = {
  today: '当日',
  '7d': '7天',
  '30d': '30天',
  '90d': '90天',
  ytd: '年初至今',
  '1y': '1年',
  '3y': '3年',
  '5y': '5年',
  dayK: '日K',
  quarterK: '季K',
  yearK: '年K',
}
const FX_RANGE_TITLE: Partial<Record<AssetDetailRangeKey, string>> = {
  today: '当日分时曲线',
  '7d': '最近7日分时曲线',
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

export function FxDetail({ symbol, inverse }: { symbol: string; inverse: boolean }) {
  const goBack = useView(s => s.goBack)
  const [range, setRange] = useState<AssetDetailRangeKey>('today')
  const pair = findForexPair(symbol)
  const display = forexDisplay(pair, inverse)
  const chartType: ChartType = isKRange(range) ? 'candle' : 'line'

  const seriesQ = useQuery({
    queryKey: ['fx-detail', symbol, inverse, range],
    queryFn: () => {
      if (isKRange(range)) return api.fxKline(symbol, klinePeriod(range))
      return api.fx(symbol, range as RangeKey)
    },
    refetchInterval: range === 'today' ? 60 * 1000 : false,
  })

  const data = useMemo(() => {
    if (!seriesQ.data) return undefined
    return inverse ? invertAssetSeries(seriesQ.data, pair) : seriesQ.data
  }, [seriesQ.data, inverse, pair])
  const last = latestRate(data)
  const delta = data ? intradayDelta(data) : null
  const sourceText = data?.quote ? quoteSourceText(data.quote.source) : null
  const asOfText = data?.quote?.as_of ? formatQuoteTime(data.quote.as_of) : null
  const noticeText = data?.notices
    ?.filter(notice => notice.kind === 'fx_kline_source_change')
    .map(notice => notice.text)
    .join(' · ') || null
  const decimals = last != null && last > 100 ? 3 : 5

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
          <div className="text-xs uppercase tracking-wider text-ink-dim">
            外汇
          </div>
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
            <h1 className="max-w-[14rem] truncate text-lg font-semibold sm:max-w-none sm:text-2xl">
              {display.name}
            </h1>
            <span className="font-mono text-xs text-ink-faint sm:text-sm">
              {display.code}
            </span>
            {last != null && (
              <>
                <span className="font-mono text-sm tabular-nums sm:text-xl">
                  {fmtNumber(last, decimals)}
                </span>
                <span className={`font-mono text-xs tabular-nums sm:text-sm ${delta == null ? 'text-ink-faint' : trendColor(delta)}`}>
                  {delta == null ? '—' : fmtSignedPct(delta)}
                </span>
              </>
            )}
          </div>
          {(sourceText || asOfText || data?.display_timezone || noticeText) && (
            <div className="mt-1 text-xs text-ink-faint">
              {[data?.display_timezone, noticeText, sourceText, asOfText].filter(Boolean).join(' · ')}
            </div>
          )}
        </div>
      </header>

      <div className="flex h-full flex-col gap-3 rounded-xl border border-border
                      bg-bg-card p-4 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-1 overflow-x-auto scrollbar-hide">
            {FX_RANGES.map(r => {
              const active = r === range
              return (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  title={FX_RANGE_TITLE[r]}
                  className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium
                              transition-colors min-h-[32px]
                              ${active
                                ? 'bg-accent text-white'
                                : 'text-ink-dim hover:bg-bg-elev hover:text-ink'}`}
                >
                  {FX_RANGE_LABEL[r]}
                </button>
              )
            })}
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
              trendValue={range === 'today' || range === '7d' ? delta : null}
              priceDigits={decimals}
            />
          )}
        </div>
      </div>
    </motion.div>
  )
}
