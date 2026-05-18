export const METRIC_EXPLANATIONS = {
  holdingCumulative: '买入持有口径：在所选窗口第一天按当前权重一次性买入，当前值相对初始资金的累计收益。',
  holdingAnnualized: '买入持有累计收益按窗口长度折算的年化复合收益率；当日窗口太短，前端不展示。',
  dcaLatest: '定投最新：最终资产净值相对累计投入本金的累计收益，反映这段回测结束时总共赚或亏了多少。',
  dcaAnnualized: '定投资金年化：按每次投入现金流计算出的 IRR。分批投入时，每笔钱持有时间不同，所以 1 年窗口下也不等同于累计收益。',
  volatility: '波动率 / 标准差：收益率的年化标准差，用来衡量价格波动风险；数值越高，波动越大。',
  maxDrawdown: '最大回撤 / MDD：从历史高点跌到随后低点的最大跌幅，用来衡量最差下行幅度。',
  benchmarkLatest: '基准最新：默认组合基准或手动选择基准在同一窗口的买入持有累计收益，用于和组合表现对比。',
  benchmarkMaxDrawdown: '基准最大回撤：基准曲线在同一窗口内从高点到低点的最大跌幅。',
  beta: 'Beta：标的或组合相对基准的敏感度。约等于 1 表示跟随基准，>1 通常更敏感，<1 通常更稳。',
  alpha: 'Alpha：扣除无风险利率和 Beta 所解释的基准收益后，组合相对基准的年化超额收益。',
  sharpe: 'Sharpe：单位波动获得的超额收益，计算口径为（年化收益 - 无风险利率）/ 年化波动率；越高通常越好。',
  riskFreeRate: '无风险利率 Rf：用于 Alpha 和 Sharpe 计算的年化低风险收益率。默认取 BIL.US 近一年年化收益，不可用时回落到常数。',
  weight: '权重：该标的在当前权重方案中的目标投资比例。滚动回测中，新投入资金使用当前执行窗口权重。',
  costPrice: '成本价：当前回测成交明细中，该标的按原币种买入价和股数加权得到的平均买入成本；这是模拟成本，不代表真实券商持仓成本。',
  latestPrice: '最新价：数据源返回的最新成交价或最近官方收盘价，按标的原币种展示。',
  currency: '币种：标的交易或计价使用的本地货币。',
  usdConverted: 'USD 折算：用对应汇率把原币种价格换算为美元，便于跨市场组合统一比较。',
  dailyChange: '当日涨跌：最新价相对上一交易日收盘价的涨跌幅，不随所选时间尺度变成区间收益。',
  periodReturnUsd: '区间收益 (USD)：组合详情页按回测成交明细的美元加权成本计算，即现价USD / 成本USD - 1；可能同时受买入汇率、最新估值汇率和价格变化影响。',
  closeness: '贴近度：FTOPSIS 中相对理想解的接近程度，越接近 1 表示综合指标越接近理想方案。',
  annualizedRoi: '年化收益：训练窗口内价格收益按一年折算后的复合收益率。',
  dividendYield: '股息率：近一年现金分红合计除以当前价格；数据源未提供分红时显示为空。',
  drawdownDuration: '回撤天数：从高点进入最大回撤到恢复至高点的持续天数；未恢复时统计到窗口末尾。',
  recoveryTime: '恢复天数：从最大回撤低点恢复至前高所需天数；未恢复时统计到窗口末尾。',
  week52High: '52周新高：最近约一年内出现过的最高价格。',
  week52Low: '52周新低：最近约一年内出现过的最低价格。',
  peRatio: 'PE (TTM)：市盈率，股价除以过去 12 个月每股收益；用于粗略衡量估值高低。',
  marketCap: '市值：公司总股本乘以当前股价，表示市场给公司的总估值。',
  volume: '成交量：最近交易时段内成交的股数或份额数量。',
  openPrice: '开盘价：当前或最近交易日第一笔交易附近的价格。',
  dayHigh: '当日最高：当前或最近交易日内出现过的最高价格。',
  dayLow: '当日最低：当前或最近交易日内出现过的最低价格。',
  previousClose: '前收盘：上一交易日的官方收盘价，常用于计算当日涨跌。',
  benchmarkReturn: '基准：用于对比的指数或组合基准收益曲线。',
  buyPrice: '买入价：回测在该买入日使用的成交价格，日线用开盘价，当日分时用首根分时开盘价。',
  fxRate: '汇率：买入或估值时使用的 USD 对本地货币汇率，用于把本地价格折算为美元。',
  usdPrice: '美元价：原币种买入价按当时汇率折算后的美元价格。',
  sharesBought: '本次股数：该次定投实际买入的股数，会受每手股数和资金不足影响。',
  totalShares: '当时总股数：该笔买入完成后，回测账户持有该标的的累计股数。',
} as const

export type MetricExplanationKey = keyof typeof METRIC_EXPLANATIONS

export function indicatorExplanation(name: string): string | undefined {
  switch (name) {
    case 'annualized_roi': return METRIC_EXPLANATIONS.annualizedRoi
    case 'dividend_yield': return METRIC_EXPLANATIONS.dividendYield
    case 'max_drawdown': return METRIC_EXPLANATIONS.maxDrawdown
    case 'drawdown_duration': return METRIC_EXPLANATIONS.drawdownDuration
    case 'recovery_time': return METRIC_EXPLANATIONS.recoveryTime
    case 'volatility': return METRIC_EXPLANATIONS.volatility
    case 'beta': return METRIC_EXPLANATIONS.beta
    default: return undefined
  }
}

export function withContext(explanation: string, context?: string | null): string {
  return context ? `${explanation}\n${context}` : explanation
}
