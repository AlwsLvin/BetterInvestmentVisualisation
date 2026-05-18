import { useEffect, useMemo, useRef } from 'react'
import { echarts } from '@/utils/echarts'
import { useChartTokens, withAlpha } from '@/utils/chartTokens'
import type { IntradaySeries } from '@/api/types'

interface Props {
  series: IntradaySeries
  className?: string
  height?: string | number
  trendValue?: number | null
}

export function MiniIntradayChart({
  series, className, height = '100%', trendValue,
}: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const tokens = useChartTokens()

  const option = useMemo(() => {
    const points = [...series.points].sort(
      (a, b) => new Date(a.datetime).getTime() - new Date(b.datetime).getTime(),
    )
    const first = points[0]?.close ?? 0
    const last = points[points.length - 1]?.close ?? 0
    const trend = trendValue != null && Number.isFinite(trendValue)
      ? trendValue
      : last - first
    const lineColor = trend >= 0 ? tokens.up : tokens.down

    return {
      animation: false,
      grid: { left: 0, right: 0, top: 2, bottom: 0 },
      xAxis: {
        type: 'time',
        show: false,
        boundaryGap: false,
      },
      yAxis: {
        type: 'value',
        scale: true,
        show: false,
      },
      series: [{
        type: 'line',
        data: points.map(p => [p.datetime, p.close]),
        smooth: 0.2,
        symbol: 'none',
        lineStyle: { width: 1.8, color: lineColor },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: withAlpha(lineColor, 0.22) },
              { offset: 1, color: withAlpha(lineColor, 0) },
            ],
          },
        },
      }],
    }
  }, [series, tokens, trendValue])

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
