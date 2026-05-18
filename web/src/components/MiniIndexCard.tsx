import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { MiniIntradayChart } from './MiniIntradayChart'
import { fmtSignedPct, fmtNumber, trendColor } from '@/utils/format'

interface Props {
  symbol: string
  label: string
  onClick?: () => void
}

export function MiniIndexCard({ symbol, label, onClick }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['intraday-index', symbol],
    queryFn: () => api.indexIntraday(symbol),
    staleTime: 60 * 1000,
    refetchInterval: 60 * 1000,
  })

  const first = data?.points[0]?.close ?? 0
  const intradayLast = data?.points[data.points.length - 1]?.close ?? 0
  const last = data?.quote?.last_price ?? intradayLast
  const delta = data?.quote?.change_pct ?? (first > 0 ? (intradayLast - first) / first : 0)
  const statusLabel = data?.market_status && data.ref_day
    ? formatMarketStatus(data.ref_day, data.market_status)
    : null

  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex h-full w-full flex-col gap-1 overflow-hidden
                 rounded-xl border border-border bg-bg-card
                 px-3 pt-2 pb-2 text-left transition-colors
                 hover:bg-bg-elev focus:outline-none focus:ring-2
                 focus:ring-accent active:scale-[0.99]
                 min-h-tap"
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-1">
            <span className="truncate text-xs uppercase tracking-wider text-ink-dim">
              {label}
            </span>
            {statusLabel && (
              <span
                className={`shrink-0 rounded border px-1 py-0.5 text-[10px] leading-none
                            ${data?.market_status === 'open'
                              ? 'border-accent-up/40 bg-accent-up/10 text-accent-up'
                              : 'border-border bg-bg-elev text-ink-faint'}`}
                title={data?.ref_day ? `行情参考日：${data.ref_day}` : undefined}
              >
                {statusLabel}
              </span>
            )}
          </div>
          <div className="font-mono text-base font-semibold tabular-nums">
            {isLoading ? '…' : isError ? 'err' : fmtNumber(last, 2)}
          </div>
        </div>
        <div className={`shrink-0 font-mono text-sm tabular-nums ${trendColor(delta)}`}>
          {isLoading ? '' : isError ? '—' : fmtSignedPct(delta)}
        </div>
      </div>

      <div className="flex-1 min-h-[40px]">
        {data && data.points.length >= 2 && (
          <MiniIntradayChart series={data} trendValue={delta} />
        )}
      </div>
    </button>
  )
}

function formatMarketStatus(refDay: string, status: 'open' | 'closed') {
  const parts = refDay.split('-')
  if (parts.length !== 3) return status === 'open' ? '开盘' : '已收盘'
  const month = Number(parts[1])
  const day = Number(parts[2])
  if (!Number.isFinite(month) || !Number.isFinite(day)) {
    return status === 'open' ? '开盘' : '已收盘'
  }
  return `${month}月${day}日${status === 'open' ? '开盘' : '已收盘'}`
}
