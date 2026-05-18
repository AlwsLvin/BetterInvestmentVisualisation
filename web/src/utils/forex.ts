import type { AssetSeries, IntradaySeries, OHLCPoint, PricePoint, QuoteSnapshot } from '@/api/types'

export interface ForexPair {
  symbol: string
  baseCode: string
  quoteCode: string
  baseName: string
  quoteName: string
}

export interface ForexDisplay {
  name: string
  code: string
  symbol: string
}

export const FX_PAIRS: ForexPair[] = [
  { symbol: 'USDCNH=X', baseCode: 'USD', quoteCode: 'CNH', baseName: '美元', quoteName: '离岸人民币' },
  { symbol: 'USDHKD=X', baseCode: 'USD', quoteCode: 'HKD', baseName: '美元', quoteName: '港元' },
  { symbol: 'USDJPY=X', baseCode: 'USD', quoteCode: 'JPY', baseName: '美元', quoteName: '日元' },
  { symbol: 'EURUSD=X', baseCode: 'EUR', quoteCode: 'USD', baseName: '欧元', quoteName: '美元' },
  { symbol: 'GBPUSD=X', baseCode: 'GBP', quoteCode: 'USD', baseName: '英镑', quoteName: '美元' },
  { symbol: 'AUDUSD=X', baseCode: 'AUD', quoteCode: 'USD', baseName: '澳元', quoteName: '美元' },
  { symbol: 'USDCAD=X', baseCode: 'USD', quoteCode: 'CAD', baseName: '美元', quoteName: '加元' },
  { symbol: 'USDCHF=X', baseCode: 'USD', quoteCode: 'CHF', baseName: '美元', quoteName: '瑞士法郎' },
]

export function findForexPair(symbol: string): ForexPair {
  const normalized = symbol.trim().toUpperCase()
  return FX_PAIRS.find(pair => pair.symbol === normalized) ?? FX_PAIRS[0]
}

export function forexDisplay(pair: ForexPair, inverse: boolean): ForexDisplay {
  return inverse ? {
    name: `${pair.quoteName}/${pair.baseName}`,
    code: `${pair.quoteCode}/${pair.baseCode}`,
    symbol: `${pair.quoteCode}/${pair.baseCode}`,
  } : {
    name: `${pair.baseName}/${pair.quoteName}`,
    code: `${pair.baseCode}/${pair.quoteCode}`,
    symbol: pair.symbol,
  }
}

export function invertIntradaySeries(series: IntradaySeries, pair: ForexPair): IntradaySeries {
  const quote = invertQuote(series.quote)
  return {
    ...series,
    symbol: forexDisplay(pair, true).symbol,
    quote,
    points: series.points
      .filter(point => point.close > 0)
      .map(point => ({
        datetime: point.datetime,
        close: 1 / point.close,
      })),
  }
}

export function invertAssetSeries(series: AssetSeries, pair: ForexPair): AssetSeries {
  return {
    ...series,
    symbol: forexDisplay(pair, true).symbol,
    quote: invertQuote(series.quote),
    points: series.points
      .filter(point => point.close > 0)
      .map(invertPricePoint),
    ohlc: series.ohlc
      ? series.ohlc.filter(validOhlcForInverse).map(invertOhlcPoint)
      : series.ohlc,
  }
}

export function intradayDelta(series: IntradaySeries | AssetSeries): number | null {
  if (
    series.quote?.last_price != null
    && series.quote.previous_close != null
    && series.quote.previous_close > 0
  ) {
    return series.quote.last_price / series.quote.previous_close - 1
  }
  const points = 'datetime' in ((series as IntradaySeries).points[0] ?? {})
    ? (series as IntradaySeries).points.map(point => point.close)
    : (series as AssetSeries).points.map(point => point.close)
  const clean = points.filter(point => point > 0)
  const first = clean[0]
  const last = clean[clean.length - 1]
  if (!first || !last) return null
  return last / first - 1
}

export function latestRate(series?: IntradaySeries | AssetSeries): number | undefined {
  return series?.quote?.last_price ?? series?.points.at(-1)?.close
}

export function quoteSourceText(source: string): string {
  if (source.includes('quote')) return 'Quote'
  if (source.includes('daily_close')) return '日线收盘'
  if (source.includes('intraday')) return '分时'
  return source
}

export function formatQuoteTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function invertQuote(quote?: QuoteSnapshot | null): QuoteSnapshot | null | undefined {
  if (!quote) return quote
  const last = quote.last_price && quote.last_price > 0 ? 1 / quote.last_price : null
  const previous = quote.previous_close && quote.previous_close > 0
    ? 1 / quote.previous_close
    : null
  return {
    ...quote,
    last_price: last,
    previous_close: previous,
    change_pct: last != null && previous != null && previous > 0
      ? last / previous - 1
      : null,
    source: `${quote.source}:inverse`,
  }
}

function invertPricePoint(point: PricePoint): PricePoint {
  return {
    ...point,
    close: 1 / point.close,
    open: point.open && point.open > 0 ? 1 / point.open : point.open,
  }
}

function validOhlcForInverse(point: OHLCPoint) {
  return point.open > 0 && point.high > 0 && point.low > 0 && point.close > 0
}

function invertOhlcPoint(point: OHLCPoint): OHLCPoint {
  return {
    ...point,
    open: 1 / point.open,
    high: 1 / point.low,
    low: 1 / point.high,
    close: 1 / point.close,
  }
}
