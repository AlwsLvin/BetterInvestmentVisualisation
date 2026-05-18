import { useEffect, useRef } from 'react'
import { echarts } from '@/utils/echarts'
import { useChartTokens, withAlpha } from '@/utils/chartTokens'
import type { AssetSeries, DividendPoint, OHLCPoint, PricePoint } from '@/api/types'

export type ChartType = 'line' | 'candle'

interface Props {
  series: AssetSeries
  type: ChartType
  className?: string
  height?: string | number
  latestPrice?: number | null
  averageCost?: number | null
  trendValue?: number | null
  priceDigits?: number
}

type Tokens = ReturnType<typeof useChartTokens>
type ZoomValue = string | number
type ZoomState = {
  start: number
  end: number
  startValue?: ZoomValue | null
  endValue?: ZoomValue | null
}
type KlineRenderMode = 'line' | 'candle'
type ReferenceValues = { latestPrice: number | null; averageCost: number | null }
type AxisExtent = { min: number; max: number }
type PointerPoint = { x: number; y: number }
type KlinePointerState = {
  isPointerDown: boolean
  moved: boolean
  detailMode: boolean
  activeLongPress: boolean
  start: PointerPoint | null
  last: PointerPoint | null
  timer: ReturnType<typeof setTimeout> | null
}

const READABLE_CANDLE_COUNT = 90
const AXIS_PADDING_RATIO = 0.01
const LATEST_LINE_COLOR = '#60A5FA'
const COST_LINE_COLOR = '#FCA5A5'
const DATA_ZOOM_ID = 'asset-chart-inside-zoom'
const LONG_PRESS_MS = 420
const DRAG_THRESHOLD_PX = 5

export function AssetChart({
  series, type, className, height = '100%', latestPrice, averageCost, trendValue, priceDigits,
}: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const zoomRef = useRef<ZoomState>({ start: 0, end: 100 })
  const modeRef = useRef<KlineRenderMode | null>(null)
  const pointerRef = useRef<KlinePointerState>(emptyKlinePointerState())
  const tokens = useChartTokens()
  const references = normalizeReferences(latestPrice, averageCost)
  const latestRef = useRef({ series, type, tokens, references, trendValue, priceDigits })
  latestRef.current = { series, type, tokens, references, trendValue, priceDigits }

  useEffect(() => {
    zoomRef.current = defaultZoomForSeries(series, type)
  }, [series.symbol, series.range, type, series.ohlc?.length])

  useEffect(() => {
    if (!ref.current) return
    const inst = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    chartRef.current = inst
    const onDataZoom = (event: any) => {
      const payload = event?.batch?.[0] ?? event
      const next = zoomStateFromPayload(payload, zoomRef.current, inst)
      if (zoomChanged(next, zoomRef.current)) {
        zoomRef.current = next
        const latest = latestRef.current
        if (latest.type === 'candle' && latest.series.ohlc && latest.series.ohlc.length > 0) {
          const labels = latest.series.ohlc.map(klineLabel)
          const nextMode = klineRenderMode(latest.series.ohlc.length, next, labels)
          const modeChanged = nextMode !== modeRef.current
          inst.setOption(
            klineZoomPatch(
              latest.series.ohlc,
              latest.series.dividends ?? null,
              latest.tokens,
              next,
              nextMode,
              latest.references,
              labels,
              latest.priceDigits,
              modeChanged,
            ),
            modeChanged ? { replaceMerge: ['series'] } : undefined,
          )
          modeRef.current = nextMode
        } else {
          inst.setOption(lineZoomPatch(latest.series.points, latest.tokens, next, latest.priceDigits))
        }
      }
    }
    inst.on('datazoom', onDataZoom)
    const isKline = () => {
      const latest = latestRef.current
      return latest.type === 'candle' && !!latest.series.ohlc?.length
    }
    const onMouseDown = (event: any) => {
      if (!isKline()) return
      if (event?.event?.button != null && event.event.button !== 0) return
      const point = pointerPointFromEvent(event)
      if (!point) return
      const state = pointerRef.current
      clearLongPress(state)
      state.isPointerDown = true
      state.moved = false
      state.activeLongPress = false
      state.start = point
      state.last = point
      if (state.detailMode) {
        showKlineTip(inst, point)
        return
      }
      state.timer = setTimeout(() => {
        if (!state.isPointerDown || state.moved || !isKline()) return
        state.detailMode = true
        state.activeLongPress = true
        setInsideZoomPan(inst, false)
        showKlineTip(inst, state.last ?? point)
      }, LONG_PRESS_MS)
    }
    const onMouseMove = (event: any) => {
      if (!isKline()) return
      const point = pointerPointFromEvent(event)
      if (!point) return
      const state = pointerRef.current
      state.last = point
      if (state.isPointerDown && state.start) {
        const movedFar = pointerDistance(state.start, point) >= DRAG_THRESHOLD_PX
        if (movedFar && state.detailMode && !state.activeLongPress) {
          state.moved = true
          clearLongPress(state)
          exitKlineDetailMode(state, inst)
          return
        }
        if (movedFar && !state.detailMode) {
          state.moved = true
          clearLongPress(state)
          return
        }
      }
      if (state.detailMode) showKlineTip(inst, point)
    }
    const onMouseUp = (event: any) => {
      if (!isKline()) return
      const point = pointerPointFromEvent(event)
      const state = pointerRef.current
      clearLongPress(state)
      state.isPointerDown = false
      state.moved = false
      state.activeLongPress = false
      state.start = null
      if (point) {
        state.last = point
        if (state.detailMode) showKlineTip(inst, point)
      }
    }
    const onGlobalOut = () => {
      const state = pointerRef.current
      clearLongPress(state)
      state.isPointerDown = false
      state.moved = false
      state.activeLongPress = false
      state.start = null
      if (state.detailMode) inst.dispatchAction({ type: 'hideTip' })
    }
    const zr = inst.getZr()
    zr.on('mousedown', onMouseDown)
    zr.on('mousemove', onMouseMove)
    zr.on('mouseup', onMouseUp)
    zr.on('globalout', onGlobalOut)
    const ro = new ResizeObserver(() => inst.resize())
    ro.observe(ref.current)
    return () => {
      inst.off('datazoom', onDataZoom)
      zr.off('mousedown', onMouseDown)
      zr.off('mousemove', onMouseMove)
      zr.off('mouseup', onMouseUp)
      zr.off('globalout', onGlobalOut)
      resetKlineInteraction(pointerRef.current, inst)
      ro.disconnect()
      inst.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const inst = chartRef.current
    if (!inst) return
    modeRef.current = klineRenderModeForSeries(series, type, zoomRef.current)
    inst.setOption(
      assetOption(series, type, tokens, zoomRef.current, references, trendValue, priceDigits),
      { notMerge: true },
    )
    resetKlineInteraction(pointerRef.current, inst)
  }, [series, type, tokens, latestPrice, averageCost, trendValue, priceDigits])

  return <div ref={ref} className={className} style={{ height, width: '100%' }} />
}

function emptyKlinePointerState(): KlinePointerState {
  return {
    isPointerDown: false,
    moved: false,
    detailMode: false,
    activeLongPress: false,
    start: null,
    last: null,
    timer: null,
  }
}

function clearLongPress(state: KlinePointerState) {
  if (state.timer != null) {
    clearTimeout(state.timer)
    state.timer = null
  }
}

function resetKlineInteraction(state: KlinePointerState, inst: echarts.ECharts) {
  clearLongPress(state)
  state.isPointerDown = false
  state.moved = false
  state.detailMode = false
  state.activeLongPress = false
  state.start = null
  state.last = null
  setInsideZoomPan(inst, true)
  inst.dispatchAction({ type: 'hideTip' })
}

function exitKlineDetailMode(state: KlinePointerState, inst: echarts.ECharts) {
  state.detailMode = false
  state.activeLongPress = false
  setInsideZoomPan(inst, true)
  inst.dispatchAction({ type: 'hideTip' })
}

function setInsideZoomPan(inst: echarts.ECharts, enabled: boolean) {
  inst.setOption({ dataZoom: [{ id: DATA_ZOOM_ID, moveOnMouseMove: enabled }] })
}

function showKlineTip(inst: echarts.ECharts, point: PointerPoint) {
  inst.dispatchAction({ type: 'showTip', x: point.x, y: point.y })
}

function pointerPointFromEvent(event: any): PointerPoint | null {
  const native = event?.event
  const x = typeof event?.offsetX === 'number'
    ? event.offsetX
    : typeof native?.offsetX === 'number'
      ? native.offsetX
      : null
  const y = typeof event?.offsetY === 'number'
    ? event.offsetY
    : typeof native?.offsetY === 'number'
      ? native.offsetY
      : null
  return x == null || y == null ? null : { x, y }
}

function pointerDistance(a: PointerPoint, b: PointerPoint) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function clampZoom(value: number) {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, value))
}

function zoomValue(value: unknown): ZoomValue | null {
  return typeof value === 'string' || typeof value === 'number' ? value : null
}

function zoomStateFromPayload(
  payload: any,
  fallback: ZoomState,
  inst: echarts.ECharts,
): ZoomState {
  const optionZoom = currentDataZoomOption(inst)
  return {
    start: clampZoom(
      typeof payload?.start === 'number'
        ? payload.start
        : typeof optionZoom?.start === 'number'
          ? optionZoom.start
          : fallback.start,
    ),
    end: clampZoom(
      typeof payload?.end === 'number'
        ? payload.end
        : typeof optionZoom?.end === 'number'
          ? optionZoom.end
          : fallback.end,
    ),
    startValue: zoomValue(payload?.startValue ?? optionZoom?.startValue ?? fallback.startValue),
    endValue: zoomValue(payload?.endValue ?? optionZoom?.endValue ?? fallback.endValue),
  }
}

function currentDataZoomOption(inst: echarts.ECharts) {
  const option = inst.getOption() as any
  return Array.isArray(option?.dataZoom) ? option.dataZoom[0] : undefined
}

function zoomChanged(next: ZoomState, prev: ZoomState) {
  return Math.abs(next.start - prev.start) > 0.01
    || Math.abs(next.end - prev.end) > 0.01
    || String(next.startValue ?? '') !== String(prev.startValue ?? '')
    || String(next.endValue ?? '') !== String(prev.endValue ?? '')
}

function defaultZoomForSeries(series: AssetSeries, type: ChartType): ZoomState {
  const total = type === 'candle' ? (series.ohlc?.length ?? 0) : 0
  if (total > READABLE_CANDLE_COUNT) {
    return {
      start: clampZoom(((total - READABLE_CANDLE_COUNT) / total) * 100),
      end: 100,
    }
  }
  return { start: 0, end: 100 }
}

function assetOption(
  series: AssetSeries,
  type: ChartType,
  tokens: Tokens,
  zoom: ZoomState,
  references: ReferenceValues,
  trendValue?: number | null,
  priceDigits?: number,
) {
  if (type === 'candle' && series.ohlc && series.ohlc.length > 0) {
    const labels = series.ohlc.map(klineLabel)
    return klineOption(
      series.ohlc,
      series.dividends ?? null,
      series.symbol,
      tokens,
      series.display_timezone,
      klineRenderMode(series.ohlc.length, zoom, labels),
      zoom,
      references,
      labels,
      priceDigits,
    )
  }
  return lineOption(
    series.points,
    series.dividends ?? null,
    series.symbol,
    tokens,
    series.display_timezone,
    zoom,
    series.ohlc ?? null,
    references,
    trendValue,
    priceDigits,
  )
}

function klineRenderModeForSeries(
  series: AssetSeries,
  type: ChartType,
  zoom: ZoomState,
): KlineRenderMode | null {
  if (type !== 'candle' || !series.ohlc || series.ohlc.length === 0) return null
  return klineRenderMode(series.ohlc.length, zoom, series.ohlc.map(klineLabel))
}

function klineRenderMode(
  total: number,
  zoom: ZoomState,
  labels?: string[],
): KlineRenderMode {
  return visibleItemCount(total, zoom, labels) > READABLE_CANDLE_COUNT ? 'line' : 'candle'
}

function visibleItemCount(total: number, zoom: ZoomState, labels?: string[]) {
  const range = visibleIndexRange(total, zoom, labels)
  return range.endIndex - range.startIndex
}

function visibleIndexRange(total: number, zoom: ZoomState, labels?: string[]) {
  if (total <= 0) return { startIndex: 0, endIndex: 0 }
  const valueRange = visibleValueIndexRange(total, zoom, labels)
  if (valueRange) return valueRange
  const startPercent = Math.min(clampZoom(zoom.start), clampZoom(zoom.end))
  const endPercent = Math.max(clampZoom(zoom.start), clampZoom(zoom.end))
  const startIndex = Math.min(
    total - 1,
    Math.max(0, Math.floor(total * startPercent / 100 + 1e-6)),
  )
  const endIndex = Math.min(
    total,
    Math.max(startIndex + 1, Math.ceil(total * endPercent / 100 - 1e-6)),
  )
  return { startIndex, endIndex }
}

function visibleValueIndexRange(total: number, zoom: ZoomState, labels?: string[]) {
  const start = indexFromZoomValue(zoom.startValue, total, labels)
  const end = indexFromZoomValue(zoom.endValue, total, labels)
  if (start == null || end == null) return null
  const startIndex = Math.min(total - 1, Math.max(0, Math.min(start, end)))
  const endIndex = Math.min(total, Math.max(start, end) + 1)
  return { startIndex, endIndex: Math.max(startIndex + 1, endIndex) }
}

function indexFromZoomValue(
  value: ZoomValue | null | undefined,
  total: number,
  labels?: string[],
) {
  if (value == null) return null
  const labelIndex = labels?.indexOf(String(value)) ?? -1
  if (labelIndex >= 0) return labelIndex
  if (typeof value === 'number' && Number.isInteger(value) && value >= 0 && value < total) {
    return value
  }
  return null
}

function visibleOhlcExtent(ohlc: OHLCPoint[], zoom: ZoomState, labels?: string[]) {
  const range = visibleIndexRange(ohlc.length, zoom, labels)
  let low = Infinity
  let high = -Infinity
  for (const point of ohlc.slice(range.startIndex, range.endIndex)) {
    if (Number.isFinite(point.low)) low = Math.min(low, point.low)
    if (Number.isFinite(point.high)) high = Math.max(high, point.high)
  }
  if (!Number.isFinite(low) || !Number.isFinite(high)) return null
  return { min: low, max: high }
}

function visibleLineExtent(points: PricePoint[], zoom: ZoomState) {
  const range = visibleIndexRange(points.length, zoom, points.map(p => p.date))
  let low = Infinity
  let high = -Infinity
  for (const point of points.slice(range.startIndex, range.endIndex)) {
    if (!Number.isFinite(point.close)) continue
    low = Math.min(low, point.close)
    high = Math.max(high, point.close)
  }
  if (!Number.isFinite(low) || !Number.isFinite(high)) return null
  return { min: low, max: high }
}

function normalizeReferences(
  latestPrice?: number | null,
  averageCost?: number | null,
): ReferenceValues {
  return {
    latestPrice: cleanReferencePrice(latestPrice),
    averageCost: cleanReferencePrice(averageCost),
  }
}

function emptyReferences(): ReferenceValues {
  return { latestPrice: null, averageCost: null }
}

function cleanReferencePrice(value?: number | null) {
  return value != null && Number.isFinite(value) && value > 0 ? value : null
}

function paddedAxisExtent(extent: AxisExtent | null, priceDigits?: number): AxisExtent | null {
  if (!extent) return null
  const min = Math.min(extent.min, extent.max)
  const max = Math.max(extent.min, extent.max)
  const span = max - min
  const padding = span > 0
    ? span * AXIS_PADDING_RATIO
    : Math.max(Math.abs(max) * AXIS_PADDING_RATIO, 0.01)
  const rawMin = min - padding
  const rawMax = max + padding
  const digits = Math.max(axisPriceDigits(rawMin, priceDigits), axisPriceDigits(rawMax, priceDigits))
  const unit = 10 ** -digits
  return {
    min: Number((Math.floor(rawMin / unit) * unit).toFixed(digits)),
    max: Number((Math.ceil(rawMax / unit) * unit).toFixed(digits)),
  }
}

function axisPriceDigits(value: number, override?: number) {
  if (override != null && Number.isFinite(override)) {
    return Math.max(0, Math.min(8, Math.round(override)))
  }
  const abs = Math.abs(value)
  if (abs >= 1) return 2
  if (abs >= 0.01) return 4
  return 6
}

function formatAxisPrice(value: number, priceDigits?: number) {
  const digits = axisPriceDigits(value, priceDigits)
  if (priceDigits != null) return value.toFixed(digits)
  return value.toFixed(digits).replace(/\.?0+$/, '')
}

function referenceLineSeries(categories: string[], references: ReferenceValues) {
  const lines = []
  if (references.latestPrice != null) {
    lines.push({
      name: '最新价',
      type: 'line',
      data: categories.map(() => references.latestPrice),
      symbol: 'none',
      silent: true,
      animation: false,
      lineStyle: { color: withAlpha(LATEST_LINE_COLOR, 0.78), type: 'dashed', width: 1.2 },
      tooltip: { show: false },
      emphasis: { disabled: true },
      z: 4,
    })
  }
  if (references.averageCost != null) {
    lines.push({
      name: '平均成本',
      type: 'line',
      data: categories.map(() => references.averageCost),
      symbol: 'none',
      silent: true,
      animation: false,
      lineStyle: { color: withAlpha(COST_LINE_COLOR, 0.78), type: 'dashed', width: 1.2 },
      tooltip: { show: false },
      emphasis: { disabled: true },
      z: 4,
    })
  }
  return lines
}

function _buildDividendIndex(divs: DividendPoint[] | null): Map<string, number> {
  const map = new Map<string, number>()
  if (!divs) return map
  for (const d of divs) map.set(d.date, d.amount)
  return map
}

function _markPoints(
  divs: DividendPoint[] | null,
  byDate: (date: string) => number | undefined,
  tokens: Tokens,
) {
  if (!divs || divs.length === 0) return undefined
  const data = divs
    .map(d => {
      const y = byDate(d.date)
      if (y == null) return null
      return {
        coord: [d.date, y] as [string, number],
        value: `+${d.amount.toFixed(3)}`,
        itemStyle: { color: tokens.up },
      }
    })
    .filter(Boolean) as { coord: [string, number]; value: string; itemStyle: { color: string } }[]
  if (data.length === 0) return undefined
  return {
    symbol: 'circle',
    symbolSize: 9,
    label: { show: false },
    itemStyle: { borderColor: tokens.tooltipBg, borderWidth: 1.5 },
    data,
  }
}

function lineOption(
  points: PricePoint[],
  divs: DividendPoint[] | null,
  symbol: string,
  tokens: Tokens,
  displayTimezone?: string | null,
  zoom: ZoomState = { start: 0, end: 100 },
  ohlc: OHLCPoint[] | null = null,
  references: ReferenceValues = emptyReferences(),
  trendValue?: number | null,
  priceDigits?: number,
) {
  const dates = points.map(p => p.date)
  const closes = points.map(p => p.close)
  const tzLabel = displayTimezone ? ` (${displayTimezone})` : ''
  const closeByDate = new Map(points.map(p => [p.date, p.close]))
  const ohlcByDate = new Map((ohlc ?? []).map(p => [p.date, p]))
  const first = closes[0] ?? 0
  const last = closes[closes.length - 1] ?? 0
  const trend = trendValue != null && Number.isFinite(trendValue)
    ? trendValue
    : last - first
  const isUp = trend >= 0
  const lineColor = isUp ? tokens.up : tokens.down
  const divIdx = _buildDividendIndex(divs)

  return {
    animation: false,
    grid: { left: 50, right: 16, top: 16, bottom: 30, containLabel: false },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: tokens.axisLine } },
      axisLabel: { color: tokens.axisLabel, fontSize: 10, hideOverlap: true },
    },
    yAxis: priceYAxis(visibleLineExtent(points, zoom), tokens, priceDigits),
    dataZoom: dataZoom(zoom),
    tooltip: {
      trigger: 'axis',
      triggerOn: 'mousemove|click',
      confine: true,
      appendToBody: true,
      backgroundColor: tokens.tooltipBg,
      borderColor: tokens.tooltipBorder,
      borderWidth: 1,
      textStyle: { color: tokens.tooltipText, fontSize: 12 },
      extraCssText: 'z-index:70;max-width:min(260px,calc(100vw - 24px));white-space:normal;',
      axisPointer: { type: 'cross', lineStyle: { color: tokens.accent } },
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        if (!p) return ''
        const div = divIdx.get(p.axisValue)
        const row = ohlcByDate.get(p.axisValue)
        if (row) {
          let html = ohlcTooltipHtml(
            row,
            previousCloseForIndex(ohlc ?? [], p.dataIndex),
            symbol,
            tokens,
            tzLabel,
            priceDigits,
          )
          if (div != null) html += dividendHtml(div, tokens)
          return html
        }
        const close = Number(p.data)
        let html = `<div style="font-weight:600">${p.axisValue}${tzLabel}</div>
                    <div>${symbol}: ${formatPrice(close, priceDigits)}</div>`
        if (div != null) html += dividendHtml(div, tokens)
        return html
      },
    },
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
            { offset: 0, color: withAlpha(lineColor, 0.25) },
            { offset: 1, color: withAlpha(lineColor, 0) },
          ],
        },
      },
      markPoint: _markPoints(divs, d => closeByDate.get(d), tokens),
    }, ...referenceLineSeries(dates, references)],
  }
}

function klineOption(
  ohlc: OHLCPoint[],
  divs: DividendPoint[] | null,
  symbol: string,
  tokens: Tokens,
  displayTimezone?: string | null,
  mode: KlineRenderMode = 'candle',
  zoom: ZoomState = { start: 0, end: 100 },
  references: ReferenceValues = emptyReferences(),
  labels: string[] = ohlc.map(klineLabel),
  priceDigits?: number,
) {
  const tzLabel = displayTimezone ? ` (${displayTimezone})` : ''
  const data = ohlc.map(p => [p.open, p.close, p.low, p.high])
  const closes = ohlc.map(p => p.close)
  const closeByDate = new Map(ohlc.map(p => [p.date, p.close]))
  const indexByLabel = new Map(labels.map((label, index) => [label, index]))
  const divIdx = _buildDividendIndex(divs)

  return {
    animation: false,
    grid: { left: 50, right: 16, top: 16, bottom: 30, containLabel: false },
    xAxis: {
      type: 'category',
      data: labels,
      boundaryGap: mode === 'candle',
      axisLine: { lineStyle: { color: tokens.axisLine } },
      axisLabel: { color: tokens.axisLabel, fontSize: 10, hideOverlap: true },
    },
    yAxis: klineYAxis(ohlc, zoom, tokens, labels, priceDigits),
    dataZoom: dataZoom(zoom, 'filter'),
    tooltip: {
      trigger: 'axis',
      triggerOn: 'none',
      confine: true,
      appendToBody: true,
      backgroundColor: tokens.tooltipBg,
      borderColor: tokens.tooltipBorder,
      borderWidth: 1,
      textStyle: { color: tokens.tooltipText, fontSize: 12 },
      extraCssText: 'z-index:70;max-width:min(260px,calc(100vw - 24px));white-space:normal;',
      axisPointer: { type: 'cross', lineStyle: { color: tokens.accent } },
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        if (!p) return ''
        const axisValue = String(p.axisValue ?? p.name ?? '')
        const index = indexByLabel.get(axisValue)
        const row = index == null ? undefined : ohlc[index]
        if (!row) return ''
        const div = divIdx.get(row.date)
        let html = ohlcTooltipHtml(
          row,
          previousCloseForIndex(ohlc, index ?? 0),
          symbol,
          tokens,
          tzLabel,
          priceDigits,
        )
        if (div != null) html += dividendHtml(div, tokens)
        return html
      },
    },
    series: [
      ...klineSeries(data, closes, divs, closeByDate, tokens, mode),
      ...referenceLineSeries(labels, references),
    ],
  }
}

function klineYAxis(
  ohlc: OHLCPoint[],
  zoom: ZoomState,
  tokens: Tokens,
  labels?: string[],
  priceDigits?: number,
) {
  return priceYAxis(visibleOhlcExtent(ohlc, zoom, labels), tokens, priceDigits)
}

function priceYAxis(extent: AxisExtent | null, tokens: Tokens, priceDigits?: number) {
  const padded = paddedAxisExtent(extent, priceDigits)
  return {
    type: 'value',
    scale: true,
    min: padded?.min,
    max: padded?.max,
    axisLabel: {
      color: tokens.axisLabel,
      fontSize: 10,
      formatter: (value: number) => formatAxisPrice(value, priceDigits),
    },
    splitLine: { lineStyle: { color: tokens.splitLine } },
  }
}

function klineSeries(
  data: number[][],
  closes: number[],
  divs: DividendPoint[] | null,
  closeByDate: Map<string, number>,
  tokens: Tokens,
  mode: KlineRenderMode,
) {
  if (mode === 'candle') {
    return [{
      type: 'candlestick',
      data,
      barWidth: '55%',
      barMinWidth: 4,
      barMaxWidth: 16,
      itemStyle: {
        color: tokens.up,
        color0: tokens.down,
        borderColor: tokens.up,
        borderColor0: tokens.down,
        borderWidth: 1,
      },
      markPoint: _markPoints(divs, d => closeByDate.get(d), tokens),
    }]
  }

  const first = closes[0] ?? 0
  const last = closes[closes.length - 1] ?? 0
  const lineColor = last >= first ? tokens.up : tokens.down
  return [{
    type: 'line',
    data: closes,
    smooth: 0.16,
    symbol: 'none',
    lineStyle: { width: 2, color: lineColor },
    areaStyle: {
      color: {
        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: withAlpha(lineColor, 0.24) },
          { offset: 1, color: withAlpha(lineColor, 0) },
        ],
      },
    },
    markPoint: _markPoints(divs, d => closeByDate.get(d), tokens),
  }]
}

function klineZoomPatch(
  ohlc: OHLCPoint[],
  divs: DividendPoint[] | null,
  tokens: Tokens,
  zoom: ZoomState,
  mode: KlineRenderMode,
  references: ReferenceValues,
  labels: string[],
  priceDigits: number | undefined,
  includeSeries: boolean,
) {
  const patch: any = {
    xAxis: { boundaryGap: mode === 'candle' },
    yAxis: klineYAxis(ohlc, zoom, tokens, labels, priceDigits),
  }
  if (includeSeries) {
    const data = ohlc.map(p => [p.open, p.close, p.low, p.high])
    const closes = ohlc.map(p => p.close)
    const closeByDate = new Map(ohlc.map(p => [p.date, p.close]))
    patch.series = [
      ...klineSeries(data, closes, divs, closeByDate, tokens, mode),
      ...referenceLineSeries(labels, references),
    ]
  }
  return patch
}

function lineZoomPatch(
  points: PricePoint[],
  tokens: Tokens,
  zoom: ZoomState,
  priceDigits?: number,
) {
  return {
    yAxis: priceYAxis(visibleLineExtent(points, zoom), tokens, priceDigits),
  }
}

function dataZoom(zoom: ZoomState, filterMode: 'filter' | 'none' = 'none') {
  const option: any = {
    id: DATA_ZOOM_ID,
    type: 'inside',
    xAxisIndex: 0,
    filterMode,
    zoomOnMouseWheel: true,
    moveOnMouseWheel: false,
    moveOnMouseMove: true,
    preventDefaultMouseMove: true,
    start: zoom.start,
    end: zoom.end,
    throttle: 16,
  }
  if (zoom.startValue != null) option.startValue = zoom.startValue
  if (zoom.endValue != null) option.endValue = zoom.endValue
  return [option]
}

function klineLabel(point: OHLCPoint) {
  return point.label ?? (
    point.period_start && point.period_end && point.period_start !== point.period_end
      ? `${point.period_start} 至 ${point.period_end}`
      : point.date
  )
}

function previousCloseForIndex(points: OHLCPoint[], index: number) {
  if (index > 0) return points[index - 1]?.close
  return points[index]?.open
}

function formatPrice(value: number, priceDigits?: number) {
  const digits = priceDigits != null && Number.isFinite(priceDigits)
    ? Math.max(0, Math.min(8, Math.round(priceDigits)))
    : Math.abs(value) >= 1000 ? 2 : 4
  return value.toFixed(digits)
}

function dividendHtml(amount: number, tokens: Tokens) {
  return `<div style="color:${tokens.up}">分红 +$${amount.toFixed(3)}</div>`
}

function ohlcTooltipHtml(
  row: OHLCPoint,
  previousClose: number | undefined,
  symbol: string,
  tokens: Tokens,
  tzLabel: string,
  priceDigits?: number,
) {
  const base = previousClose && previousClose > 0 ? previousClose : row.open
  const change = row.close - base
  const changePct = base > 0 ? change / base : 0
  const color = change >= 0 ? tokens.up : tokens.down
  const title = row.period_start && row.period_end && row.period_start !== row.period_end
    ? `${klineLabel(row)} (${row.period_start} 至 ${row.period_end})`
    : klineLabel(row)
  return `<div style="font-weight:600">${title}${tzLabel}</div>
          <div>${symbol}</div>
          <div>开 ${formatPrice(row.open, priceDigits)}　收 <span style="color:${color}">${formatPrice(row.close, priceDigits)}</span></div>
          <div>高 ${formatPrice(row.high, priceDigits)}　低 ${formatPrice(row.low, priceDigits)}</div>
          <div style="color:${color}">
            涨跌 ${change >= 0 ? '+' : ''}${formatPrice(change, priceDigits)}
            (${changePct >= 0 ? '+' : ''}${(changePct * 100).toFixed(2)}%)
          </div>`
}
