import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { RangeKey } from '@/api/types'
import { IndexChart } from './IndexChart'
import { IndexStrip, type StripIndex } from './IndexStrip'
import { BacktestPanel } from './BacktestPanel'
import { ForexPanel } from './ForexPanel'
import { fmtSignedPct, fmtNumber, trendColor } from '@/utils/format'
import { useView } from '@/stores/view'
import type { TabKey } from './MarketTabs'

interface MarketConfig {
  primary: StripIndex
  strip: StripIndex[]
}

const MARKET_CONFIG: Record<Exclude<TabKey, 'watchlist' | 'fx'>, MarketConfig> = {
  cn: {
    primary: { code: '000001.SS', label: '上证综指' },
    strip: [
      { code: '000001.SS', label: '上证综指' },
      { code: '399001.SZ', label: '深证成指' },
      { code: '000300.SS', label: '沪深 300' },
    ],
  },
  us: {
    primary: { code: '^GSPC', label: '标普 500' },
    strip: [
      { code: '^GSPC', label: '标普 500' },
      { code: '^IXIC', label: '纳斯达克' },
      { code: '^DJI',  label: '道琼斯' },
    ],
  },
  hk: {
    primary: { code: '^HSI', label: '恒生指数' },
    strip: [
      { code: '^HSI',    label: '恒生指数' },
      { code: '^HSCE',   label: '恒生中国企业' },
      { code: '3033.HK', label: '恒生科技 ETF' },
    ],
  },
}

interface Props {
  tab: TabKey
  range: RangeKey
  onRangeChange: (r: RangeKey) => void
  onSearch?: (targetWatchlistId?: string) => void
}

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

export function MainPanel({ tab, range, onRangeChange, onSearch }: Props) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-border bg-bg-card p-4
                    overflow-hidden">
      {tab !== 'fx' && (
        <div className="mb-3 flex items-center justify-end">
          <RangePicker range={range} onRangeChange={onRangeChange} />
        </div>
      )}
      <div className="flex-1 min-h-0">
        {tab === 'watchlist' && <BacktestPanel range={range} onSearch={onSearch} />}
        {tab === 'fx' && <ForexPanel />}
        {tab !== 'watchlist' && tab !== 'fx' && (
          <IndexView config={MARKET_CONFIG[tab]} range={range} />
        )}
      </div>
    </div>
  )
}


function RangePicker({ range, onRangeChange }: { range: RangeKey; onRangeChange: (r: RangeKey) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto scrollbar-hide">
      {RANGES.map(r => {
        const active = r === range
        return (
          <button
            key={r}
            onClick={() => onRangeChange(r)}
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
  )
}


function IndexView({ config, range }: { config: MarketConfig; range: RangeKey }) {
  const goAsset = useView(s => s.goAsset)
  const { code, label } = config.primary
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['index', code, range],
    queryFn: () => api.index(code, range),
    refetchInterval: range === 'today' ? 60 * 1000 : false,
  })

  const intradayLast = data?.points[data.points.length - 1]?.close ?? 0
  const last = data?.quote?.last_price ?? intradayLast
  const firstPoint = data?.points[0]
  const first = firstPoint ? (firstPoint.open && firstPoint.open > 0 ? firstPoint.open : firstPoint.close) : 0
  const delta = data?.quote?.change_pct ?? (first > 0 ? (intradayLast - first) / first : 0)

  return (
    <div className="flex h-full flex-col gap-3">
      <IndexStrip indices={config.strip} onSelect={goAsset} />

      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-dim">{code}</div>
          <h2 className="text-xl font-semibold sm:text-2xl">{label}</h2>
        </div>
        {data && (
          <div className="flex items-baseline gap-3">
            <span className="font-mono text-lg font-semibold tabular-nums sm:text-2xl">
              {fmtNumber(last, 2)}
            </span>
            <span className={`font-mono text-sm tabular-nums ${trendColor(delta)}`}>
              {fmtSignedPct(delta)}
            </span>
            <button
              type="button"
              onClick={() => goAsset(code)}
              className="rounded-md border border-border bg-bg-elev px-2 py-1
                         text-xs text-ink-dim hover:text-ink min-h-[28px]
                         focus:outline-none focus:ring-2 focus:ring-accent"
            >
              详情 →
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 min-h-[220px]">
        {isLoading && (
          <div className="grid h-full place-items-center text-ink-faint text-sm">
            加载中…
          </div>
        )}
        {isError && (
          <div className="grid h-full place-items-center text-accent-down text-sm">
            加载失败：{(error as Error).message}
          </div>
        )}
        {data && <IndexChart series={data} trendValue={range === 'today' ? delta : null} />}
      </div>
    </div>
  )
}
