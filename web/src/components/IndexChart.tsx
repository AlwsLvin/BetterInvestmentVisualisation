import { useEffect, useMemo, useRef } from 'react'
import { echarts } from '@/utils/echarts'
import { useChartTokens, withAlpha } from '@/utils/chartTokens'
import type { AssetSeries } from '@/api/types'

interface Props {
  series: AssetSeries
  /** Optional dates to render as buy markers (frontend-side overlay
   *  for the M5 watchlist plan). */
  investDates?: string[]
  /** Touch-friendly tooltip on mobile (mousemove|click); pass false for
   *  decorative sparkline-only charts. */
  interactive?: boolean
  className?: string
  height?: string | number
  trendValue?: number | null
}

export function IndexChart({
  series, investDates, interactive = true, className, height = '100%', trendValue,
}: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const tokens = useChartTokens()

  const option = useMemo(() => {
    const dates = series.points.map(p => p.date)
    const closes = series.points.map(p => p.close)
    const tzLabel = series.display_timezone ? ` (${series.display_timezone})` : ''
    const first = closes[0] ?? 0
    const last = closes[closes.length - 1] ?? 0
    const trend = trendValue != null && Number.isFinite(trendValue)
      ? trendValue
      : last - first
    const isUp = trend >= 0
    const lineColor = isUp ? tokens.up : tokens.down
    const fillStrong = withAlpha(lineColor, 0.25)
    const fillFade = withAlpha(lineColor, 0)

    const markPointData = (investDates ?? [])
      .map(d => {
        const idx = dates.indexOf(d)
        if (idx < 0) return null
        return { coord: [d, closes[idx]], value: '买入' }
      })
      .filter(Boolean) as { coord: [string, number]; value: string }[]

    return {
      animation: false,
      grid: { left: 8, right: 8, top: 8, bottom: 8, containLabel: interactive },
      xAxis: {
        type: 'category',
        data: dates,
        show: interactive,
        boundaryGap: false,
        axisLine: { lineStyle: { color: tokens.axisLine } },
        axisLabel: { color: tokens.axisLabel, fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        scale: true,
        show: interactive,
        splitLine: { lineStyle: { color: tokens.splitLine } },
        axisLabel: { color: tokens.axisLabel, fontSize: 10 },
      },
      tooltip: interactive ? {
        trigger: 'axis',
        triggerOn: 'mousemove|click',
        backgroundColor: tokens.tooltipBg,
        borderColor: tokens.tooltipBorder,
        borderWidth: 1,
        textStyle: { color: tokens.tooltipText, fontSize: 12 },
        axisPointer: { type: 'cross', lineStyle: { color: tokens.accent } },
        formatter: (params: any) => {
          const p = Array.isArray(params) ? params[0] : params
          if (!p) return ''
          const close = Number(p.data)
          const pct = first > 0 ? ((close - first) / first) * 100 : 0
          return `<div style="font-weight:600">${p.axisValue}${tzLabel}</div>
                  <div>${series.symbol}: ${close.toFixed(2)}</div>
                  <div style="color:${pct >= 0 ? tokens.up : tokens.down}">
                    ${pct >= 0 ? '+' : ''}${pct.toFixed(2)}% vs start
                  </div>`
        },
      } : undefined,
      series: [{
        type: 'line',
        data: closes,
        smooth: 0.2,
        symbol: 'none',
        lineStyle: { width: 2, color: lineColor },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: fillStrong },
              { offset: 1, color: fillFade },
            ],
          },
        },
        markPoint: markPointData.length > 0 ? {
          symbol: 'pin',
          symbolSize: 28,
          itemStyle: { color: tokens.accent, borderColor: tokens.tooltipBg, borderWidth: 1 },
          label: { color: '#fff', fontSize: 9, fontWeight: 600 },
          data: markPointData,
        } : undefined,
      }],
    }
  }, [series, investDates, interactive, tokens, trendValue])

  useEffect(() => {
    if (!ref.current) return
    const inst = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    chartRef.current = inst
    inst.setOption(option)

    const ro = new ResizeObserver(() => inst.resize())
    ro.observe(ref.current)
    return () => {
      ro.disconnect()
      inst.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true })
  }, [option])

  return <div ref={ref} className={className} style={{ height, width: '100%' }} />
}
