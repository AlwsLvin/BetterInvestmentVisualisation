// Centralised ECharts setup with tree-shaken modules to keep the mobile
// bundle small. Components register once at import time.
import * as echarts from 'echarts/core'
import { CandlestickChart, LineChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, MarkPointComponent,
  MarkLineComponent, DataZoomComponent, LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  CandlestickChart,
  GridComponent,
  TooltipComponent,
  MarkPointComponent,
  MarkLineComponent,
  DataZoomComponent,
  LegendComponent,
  CanvasRenderer,
])

export { echarts }
