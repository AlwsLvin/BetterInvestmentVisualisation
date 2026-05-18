export const fmtPct = (x: number, digits = 2) =>
  `${(x * 100).toFixed(digits)}%`

export const fmtSignedPct = (x: number, digits = 2) =>
  `${x >= 0 ? '+' : ''}${(x * 100).toFixed(digits)}%`

export const fmtMoney = (x: number) =>
  x.toLocaleString('en-US', { style: 'currency', currency: 'USD',
                              maximumFractionDigits: 0 })

export const fmtNumber = (x: number, digits = 2) =>
  x.toLocaleString('en-US', { minimumFractionDigits: digits,
                              maximumFractionDigits: digits })

export const trendColor = (delta: number) =>
  delta > 0 ? 'text-accent-up' : delta < 0 ? 'text-accent-down' : 'text-ink-dim'
