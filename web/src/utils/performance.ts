import type { PricePoint } from '@/api/types'

export interface ReturnPoint {
  date: string
  return_pct: number
}

export interface HoldingReturnSeries {
  points: ReturnPoint[]
  cumulativeReturn: number
  maxDrawdown: number
}

export function holdingReturnSeries(
  points: PricePoint[],
  startDate?: string,
): HoldingReturnSeries | null {
  const startTime = startDate ? new Date(startDate).getTime() : null
  const sorted = [...points]
    .filter(p => startTime == null || new Date(p.date).getTime() >= startTime)
    .sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  )
  const first = sorted.find(p => p.close > 0)
  if (!first) return null

  const base = (first.open && first.open > 0) ? first.open : first.close
  const returns = sorted
    .filter(p => p.close > 0)
    .map(p => ({ date: p.date, return_pct: p.close / base - 1 }))

  if (returns.length === 0) return null

  let peak = 1
  let maxDrawdown = 0
  for (const p of returns) {
    const wealth = p.return_pct + 1
    peak = Math.max(peak, wealth)
    if (peak > 0) maxDrawdown = Math.max(maxDrawdown, (peak - wealth) / peak)
  }

  return {
    points: returns,
    cumulativeReturn: returns[returns.length - 1].return_pct,
    maxDrawdown,
  }
}

export function returnSeriesFromPoints(points: ReturnPoint[]): HoldingReturnSeries | null {
  const returns = [...points]
    .filter(p => Number.isFinite(p.return_pct))
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
  if (returns.length === 0) return null

  let peak = 1
  let maxDrawdown = 0
  for (const p of returns) {
    const wealth = p.return_pct + 1
    peak = Math.max(peak, wealth)
    if (peak > 0) maxDrawdown = Math.max(maxDrawdown, (peak - wealth) / peak)
  }

  return {
    points: returns,
    cumulativeReturn: returns[returns.length - 1].return_pct,
    maxDrawdown,
  }
}
