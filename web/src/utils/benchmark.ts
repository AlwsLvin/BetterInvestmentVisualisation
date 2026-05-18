import { fmtPct } from './format'

export function formatBenchmarkComponents(
  components: Record<string, number>,
  fallback = '基准',
): string {
  const entries = Object.entries(components)
    .filter(([, weight]) => Number.isFinite(weight) && weight > 0)
    .sort((a, b) => b[1] - a[1])
  if (entries.length === 0) return fallback
  return entries.map(([symbol, weight]) => `${fmtPct(weight, 1)} ${symbol}`).join(' + ')
}

export function benchmarkDetailTitle({
  customSymbol,
  components,
  fallbackLabel,
}: {
  customSymbol?: string
  components?: Record<string, number>
  fallbackLabel?: string | null
}): string {
  if (customSymbol) return `自定义基准：${customSymbol}`

  const detail = components ? formatBenchmarkComponents(components, '') : ''
  if (detail) return `默认组合基准：${detail}`
  if (fallbackLabel && !fallbackLabel.startsWith('Composite')) {
    return `默认组合基准：${fallbackLabel}`
  }
  return '默认组合基准'
}
