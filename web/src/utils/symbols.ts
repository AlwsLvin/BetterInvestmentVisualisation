export function toProjectSymbol(yahoo: string): string {
  const symbol = yahoo.trim().toUpperCase()
  if (!symbol) return symbol
  if (symbol.startsWith('^')) return symbol
  const dot = symbol.lastIndexOf('.')
  if (dot < 0) return `${symbol}.US`
  const code = symbol.slice(0, dot)
  const suffix = symbol.slice(dot + 1).toUpperCase()
  if (suffix === 'SS') return `${code}.SH`
  return `${code}.${suffix}`
}

const INDEX_SYMBOLS = new Set([
  '000001.SS', '000016.SS', '000300.SS', '000905.SS',
  '399001.SZ', '399006.SZ',
])

export function isIndexSymbol(symbol: string): boolean {
  const normalized = symbol.trim().toUpperCase().replace(/\.SH$/, '.SS')
  return normalized.startsWith('^') || INDEX_SYMBOLS.has(normalized)
}
