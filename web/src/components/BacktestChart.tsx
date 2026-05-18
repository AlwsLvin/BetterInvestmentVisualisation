import { useEffect, useMemo, useRef } from 'react'
import { echarts } from '@/utils/echarts'
import { useChartTokens, withAlpha } from '@/utils/chartTokens'
import type { BacktestResponse } from '@/api/types'
import type { HoldingReturnSeries } from '@/utils/performance'

interface BenchmarkSeries {
  label: string
  data: HoldingReturnSeries
}

interface Props {
  data: BacktestResponse
  benchmark?: BenchmarkSeries | null
  className?: string
  height?: string | number
}

export function BacktestChart({ data, benchmark, className, height = '100%' }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const tokens = useChartTokens()

  const option = useMemo(() => {
    const points = [...data.points].sort(
      (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
    )
    const dates = points.map(p => p.date)
    const returnPct = points.map(p => p.return_pct * 100)
    const navs = points.map(p => p.nav)
    const cash = points.map(p => p.cash_invested)
    const tzLabel = data.display_timezone ? ` (${data.display_timezone})` : ''
    const compactTimeAxis = !!data.display_timezone

    const isUp = (returnPct[returnPct.length - 1] ?? 0) >= 0
    const lineColor = isUp ? tokens.up : tokens.down
    const benchmarkColor = tokens.accent
    const fillStrong = withAlpha(lineColor, 0.28)
    const fillFade = withAlpha(lineColor, 0)

    const investSet = new Set(data.invest_dates)
    const markPoints = data.invest_dates
      .map(d => {
        const idx = dates.indexOf(d)
        if (idx < 0) return null
        return {
          coord: [d, returnPct[idx]] as [string, number],
          value: '买入',
        }
      })
      .filter(Boolean) as { coord: [string, number]; value: string }[]

    return {
      animation: false,
      grid: { left: 50, right: 16, top: 16, bottom: 30, containLabel: false },
      xAxis: compactTimeAxis
        ? {
            type: 'category',
            data: dates,
            boundaryGap: false,
            axisLine: { lineStyle: { color: tokens.axisLine } },
            axisLabel: { color: tokens.axisLabel, fontSize: 10, hideOverlap: true },
          }
        : {
            type: 'time',
            boundaryGap: false,
            axisLine: { lineStyle: { color: tokens.axisLine } },
            axisLabel: { color: tokens.axisLabel, fontSize: 10, hideOverlap: true },
          },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: {
          color: tokens.axisLabel,
          fontSize: 10,
          formatter: (v: number) => `${v.toFixed(2)}%`,
        },
        splitLine: { lineStyle: { color: tokens.splitLine } },
      },
      tooltip: {
        trigger: 'axis',
        triggerOn: 'mousemove|click',
        backgroundColor: tokens.tooltipBg,
        borderColor: tokens.tooltipBorder,
        borderWidth: 1,
        textStyle: { color: tokens.tooltipText, fontSize: 12 },
        axisPointer: { type: 'cross', lineStyle: { color: tokens.accent } },
        formatter: (params: any) => {
          const rows = Array.isArray(params) ? params : [params]
          const p = rows.find((item: any) => item.seriesName === '定投收益率') ?? rows[0]
          if (!p) return ''
          const idx = p.dataIndex
          const ret = returnPct[idx]
          const nav = navs[idx]
          const cashAt = cash[idx]
          const date = dates[idx]
          const isInvestDay = investSet.has(date)
          const benchmarkRow = rows.find((item: any) => item.seriesName !== '定投收益率')
          const benchmarkHtml = benchmarkRow
            ? `<div style="color:${benchmarkColor}">
                 ${benchmarkRow.seriesName} ${benchmarkRow.data[1] >= 0 ? '+' : ''}${benchmarkRow.data[1].toFixed(2)}%
               </div>`
            : ''
          return `<div style="font-weight:600">${date}${tzLabel}${isInvestDay
            ? ` <span style="color:${tokens.accent}">· 买入</span>` : ''}</div>
                  <div style="color:${ret >= 0 ? tokens.up : tokens.down}">
                    定投 ${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%
                  </div>
                  ${benchmarkHtml}
                  <div>净值 $${nav.toFixed(0)}</div>
                  <div>累投 $${cashAt.toFixed(0)}</div>`
        },
      },
      series: [{
        name: '定投收益率',
        type: 'line',
        data: points.map((p, idx) => [p.date, returnPct[idx]]),
        smooth: 0.15,
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
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: tokens.axisLine, type: 'solid', width: 1 },
          label: { show: false },
          data: [{ yAxis: 0 }],
        },
        markPoint: markPoints.length > 0 ? {
          symbol: 'pin',
          symbolSize: 24,
          itemStyle: { color: tokens.accent, borderColor: tokens.tooltipBg, borderWidth: 1 },
          label: { show: false },
          data: markPoints,
        } : undefined,
      }, ...(benchmark ? [{
        name: benchmark.label,
        type: 'line',
        data: benchmark.data.points.map(p => [p.date, p.return_pct * 100]),
        smooth: 0.12,
        symbol: 'none',
        lineStyle: { width: 1.8, color: benchmarkColor, type: 'dashed' },
        areaStyle: undefined,
      }] : [])],
    }
  }, [data, benchmark, tokens])

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
