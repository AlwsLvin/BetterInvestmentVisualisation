import { useMemo } from 'react'
import { useTheme } from '@/stores/theme'

export interface ChartTokens {
  axisLabel: string
  axisLine: string
  splitLine: string
  tooltipBg: string
  tooltipText: string
  tooltipBorder: string
  up: string
  down: string
  accent: string
  ink: string
  inkFaint: string
}

/** CSS vars are stored as RGB triplets ("91 140 255"); convert to "#5b8cff"
 *  so ECharts and our `withAlpha` helper can consume hex uniformly. */
function readVar(name: string): string {
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(name).trim()
  if (!raw) return '#000000'
  const parts = raw.split(/[\s,]+/).map(Number)
  if (parts.length === 3 && parts.every(n => !Number.isNaN(n))) {
    return '#' + parts.map(n => n.toString(16).padStart(2, '0')).join('')
  }
  return raw
}

export function readChartTokens(): ChartTokens {
  return {
    axisLabel:    readVar('--color-ink-dim'),
    axisLine:     readVar('--color-border'),
    splitLine:    readVar('--color-bg-elev'),
    tooltipBg:    readVar('--color-bg-card'),
    tooltipText:  readVar('--color-ink'),
    tooltipBorder:readVar('--color-border'),
    up:           readVar('--color-accent-up'),
    down:         readVar('--color-accent-down'),
    accent:       readVar('--color-accent'),
    ink:          readVar('--color-ink'),
    inkFaint:     readVar('--color-ink-faint'),
  }
}

/** Hook re-runs when the resolved theme changes, so chart options pick up
 *  fresh CSS-var values without manual subscription. */
export function useChartTokens(): ChartTokens {
  const resolved = useTheme(s => s.resolved)
  return useMemo(() => readChartTokens(), [resolved])
}

export function withAlpha(hex: string, alpha: number): string {
  const m = hex.match(/^#([0-9a-fA-F]{6})$/)
  if (!m) return hex
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}
