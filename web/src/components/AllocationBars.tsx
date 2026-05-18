import { motion } from 'framer-motion'
import { fmtPct } from '@/utils/format'
import { METRIC_EXPLANATIONS } from '@/utils/metricExplanations'
import { InfoTooltip } from './InfoTooltip'

interface Props {
  allocation: Record<string, number>
  closeness?: Record<string, number>
  className?: string
}

export function AllocationBars({ allocation, closeness, className = '' }: Props) {
  const sorted = Object.entries(allocation).sort((a, b) => b[1] - a[1])
  const max = sorted[0]?.[1] ?? 1
  return (
    <div className={`flex min-w-0 flex-col gap-1.5 ${className}`}>
      {sorted.map(([ticker, weight]) => {
        const widthPct = max > 0 ? (weight / max) * 100 : 0
        const cc = closeness?.[ticker]
        return (
          <div
            key={ticker}
            className="flex min-w-0 items-center gap-2 text-xs"
          >
            <div className="w-20 shrink-0 truncate font-mono text-ink-dim sm:w-24">
              {ticker}
            </div>
            <div className="relative h-5 min-w-0 flex-1 overflow-hidden rounded
                            bg-bg-elev">
              <motion.div
                layout
                initial={{ width: 0 }}
                animate={{ width: `${widthPct}%` }}
                transition={{ type: 'spring', stiffness: 200, damping: 26 }}
                className="absolute inset-y-0 left-0 bg-gradient-to-r
                           from-accent/40 to-accent"
              />
            </div>
            <div className="w-14 shrink-0 text-right font-mono tabular-nums">
              {fmtPct(weight, 1)}
            </div>
            {cc !== undefined && (
              <div className="hidden w-24 shrink-0 text-right font-mono
                              text-ink-faint tabular-nums sm:block">
                <span className="inline-flex items-center justify-end gap-1">
                  CC {cc.toFixed(3)}
                  <InfoTooltip content={METRIC_EXPLANATIONS.closeness} />
                </span>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
