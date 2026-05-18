import { create } from 'zustand'
import type { TabKey } from '@/components/MarketTabs'
import type { RangeKey } from '@/api/types'

/** Lightweight client-side view state. We avoid pulling react-router-dom in
 *  to keep the bundle small; URL sync can be added later if needed. */
export type View =
  | { type: 'home'; tab: TabKey }
  | { type: 'asset'; symbol: string; returnTab: TabKey; returnTo?: ReturnTarget }
  | { type: 'fx'; symbol: string; inverse: boolean; returnTab: TabKey }
  | { type: 'portfolio'; returnTab: TabKey; range: RangeKey; benchmarkSymbol?: string }

export type ReturnTarget =
  | { type: 'home'; tab: TabKey }
  | { type: 'portfolio'; returnTab: TabKey; range: RangeKey; benchmarkSymbol?: string }

interface State {
  view: View
  homeRange: RangeKey
  setHomeTab: (tab: TabKey) => void
  setHomeRange: (range: RangeKey) => void
  goAsset: (symbol: string, returnTo?: ReturnTarget) => void
  goFx: (symbol: string, inverse?: boolean) => void
  goPortfolio: (range?: RangeKey, benchmarkSymbol?: string) => void
  goHome: () => void
  goBack: () => void
}

const _currentTab = (v: View): TabKey =>
  v.type === 'home' ? v.tab : v.returnTab

const _returnTarget = (v: View): ReturnTarget => {
  if (v.type === 'portfolio') return { ...v }
  if (v.type === 'asset' && v.returnTo) return v.returnTo
  return { type: 'home', tab: _currentTab(v) }
}

export const useView = create<State>(set => ({
  view: { type: 'home', tab: 'watchlist' },
  homeRange: '1y',

  setHomeTab: tab => set(s => {
    if (s.view.type !== 'home') return s
    return { view: { type: 'home', tab } }
  }),

  setHomeRange: range => set({ homeRange: range }),

  goAsset: (symbol, returnTo) => set(s => ({
    view: {
      type: 'asset',
      symbol,
      returnTab: _currentTab(s.view),
      returnTo: returnTo ?? _returnTarget(s.view),
    },
  })),

  goFx: (symbol, inverse = false) => set(s => ({
    view: {
      type: 'fx',
      symbol,
      inverse,
      returnTab: _currentTab(s.view),
    },
  })),

  goPortfolio: (range = '1y', benchmarkSymbol) => set(s => ({
    view: { type: 'portfolio', returnTab: _currentTab(s.view), range, benchmarkSymbol },
  })),

  goHome: () => set(s => {
    const tab = s.view.type === 'home' ? s.view.tab : s.view.returnTab
    return { view: { type: 'home', tab } }
  }),

  goBack: () => set(s => {
    if (s.view.type === 'fx') {
      return { view: { type: 'home', tab: s.view.returnTab } }
    }
    if (s.view.type !== 'asset' || !s.view.returnTo) {
      const tab = s.view.type === 'home' ? s.view.tab : s.view.returnTab
      return { view: { type: 'home', tab } }
    }
    return { view: s.view.returnTo }
  }),
}))

export const useCurrentTab = () =>
  useView(s => s.view.type === 'home' ? s.view.tab : s.view.returnTab)
