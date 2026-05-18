import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Scheme, Style } from '@/api/types'

export interface Plan {
  amount: number
  /** "daily" | "weekly:MON" | "monthly:1" | "every:30d", etc. */
  frequency: string
}

export interface Watchlist {
  id: string
  name: string
  tickers: string[]
}

export interface PortfolioPrefs {
  style: Style
  scheme: Scheme
  tau: number
  power: number
  floor: number
}

interface State {
  watchlists: Record<string, Watchlist>
  order: string[]
  activeId: string
  plans: Record<string, Plan>
  prefs: Record<string, PortfolioPrefs>

  createWatchlist: () => string
  renameWatchlist: (id: string, name: string) => void
  setActiveWatchlist: (id: string) => void
  deleteWatchlist: (id: string) => void
  deleteWatchlists: (ids: string[]) => void
  addTicker: (id: string, ticker: string) => void
  removeTicker: (id: string, ticker: string) => void
  setPlan: (id: string, plan: Plan) => void
  setPrefs: (id: string, prefs: Partial<PortfolioPrefs>) => void
}

const DEFAULT_ID = 'default'

const DEFAULT_TICKERS = [
  'AAPL.US', 'NVDA.US', 'IAU.US',
  'BIL.US', 'KO.US', 'WMT.US', 'HSBC.US',
]

const DEFAULT_PREFS: PortfolioPrefs = {
  style: 'high_return',
  scheme: 'softmax',
  tau: 0.5,
  power: 2.0,
  floor: 0.0,
}

const normalize = (t: string) => t.trim().toUpperCase()

const DEFAULT_PLAN: Plan = { amount: 1000, frequency: 'monthly:1' }

const _orderedIds = (s: Pick<State, 'order' | 'watchlists'>) => {
  const fromOrder = s.order.filter(id => s.watchlists[id])
  const extras = Object.keys(s.watchlists).filter(id => !fromOrder.includes(id))
  return [...fromOrder, ...extras]
}

const _nextName = (s: Pick<State, 'order' | 'watchlists'>) =>
  `组合 ${_orderedIds(s).length + 1}`

const _nextId = (s: Pick<State, 'watchlists'>) => {
  let i = Object.keys(s.watchlists).length + 1
  let id = `combo-${i}`
  while (s.watchlists[id]) {
    i += 1
    id = `combo-${i}`
  }
  return id
}

const _deleteWatchlists = (
  s: Pick<State, 'watchlists' | 'order' | 'activeId' | 'plans' | 'prefs'>,
  rawIds: string[],
) => {
  const ids = new Set(rawIds.filter(id => s.watchlists[id]))
  if (ids.size === 0) return s

  const currentOrder = _orderedIds(s)
  const nextOrder = currentOrder.filter(id => !ids.has(id))
  if (nextOrder.length === 0) return s

  const watchlists = { ...s.watchlists }
  const plans = { ...s.plans }
  const prefs = { ...s.prefs }
  ids.forEach(id => {
    delete watchlists[id]
    delete plans[id]
    delete prefs[id]
  })

  return {
    watchlists,
    order: nextOrder,
    activeId: ids.has(s.activeId) ? nextOrder[0] : s.activeId,
    plans,
    prefs,
  }
}

export const useWatchlist = create<State>()(
  persist(
    set => ({
      watchlists: {
        [DEFAULT_ID]: {
          id: DEFAULT_ID,
          name: '组合 1',
          tickers: DEFAULT_TICKERS,
        },
      },
      order: [DEFAULT_ID],
      activeId: DEFAULT_ID,
      plans: { [DEFAULT_ID]: DEFAULT_PLAN },
      prefs: { [DEFAULT_ID]: DEFAULT_PREFS },

      createWatchlist: () => {
        let created = DEFAULT_ID
        set(s => {
          const id = _nextId(s)
          created = id
          return {
            watchlists: {
              ...s.watchlists,
              [id]: { id, name: _nextName(s), tickers: [] },
            },
            order: [..._orderedIds(s), id],
            plans: { ...s.plans, [id]: DEFAULT_PLAN },
            prefs: { ...s.prefs, [id]: DEFAULT_PREFS },
          }
        })
        return created
      },

      renameWatchlist: (id, raw) => set(s => {
        const current = s.watchlists[id]
        if (!current) return s
        const name = raw.trim() || current.name
        return {
          watchlists: {
            ...s.watchlists,
            [id]: { ...current, name },
          },
        }
      }),

      setActiveWatchlist: id => set(s => {
        if (!s.watchlists[id]) return s
        return { activeId: id }
      }),

      deleteWatchlist: id => set(s => _deleteWatchlists(s, [id])),

      deleteWatchlists: ids => set(s => _deleteWatchlists(s, ids)),

      addTicker: (id, raw) => set(s => {
        const ticker = normalize(raw)
        if (!ticker) return s
        const current = s.watchlists[id]
        if (!current || current.tickers.includes(ticker)) return s
        return {
          watchlists: {
            ...s.watchlists,
            [id]: { ...current, tickers: [...current.tickers, ticker] },
          },
        }
      }),

      removeTicker: (id, ticker) => set(s => {
        const current = s.watchlists[id]
        if (!current) return s
        return {
          watchlists: {
            ...s.watchlists,
            [id]: {
              ...current,
              tickers: current.tickers.filter(t => t !== ticker),
            },
          },
        }
      }),

      setPlan: (id, plan) => set(s => ({ plans: { ...s.plans, [id]: plan } })),

      setPrefs: (id, partial) => set(s => ({
        prefs: {
          ...s.prefs,
          [id]: { ...(s.prefs[id] ?? DEFAULT_PREFS), ...partial },
        },
      })),
    }),
    {
      name: 'bv-watchlist',
      version: 2,
      migrate: (persisted: unknown) => {
        const s = persisted as Partial<State>
        const watchlists = { ...(s.watchlists ?? {
          [DEFAULT_ID]: {
            id: DEFAULT_ID,
            name: '组合 1',
            tickers: DEFAULT_TICKERS,
          },
        }) }
        if (watchlists[DEFAULT_ID]?.name === '示例组合') {
          watchlists[DEFAULT_ID] = { ...watchlists[DEFAULT_ID], name: '组合 1' }
        }
        const order = (s.order && s.order.length > 0)
          ? s.order.filter(id => watchlists[id])
          : Object.keys(watchlists)
        const activeId = s.activeId && watchlists[s.activeId]
          ? s.activeId
          : (order[0] ?? DEFAULT_ID)
        return {
          ...s,
          watchlists,
          order: order.length > 0 ? order : [DEFAULT_ID],
          activeId,
          plans: { [DEFAULT_ID]: DEFAULT_PLAN, ...(s.plans ?? {}) },
          prefs: { [DEFAULT_ID]: DEFAULT_PREFS, ...(s.prefs ?? {}) },
        }
      },
    },
  ),
)

export const DEFAULT_WATCHLIST_ID = DEFAULT_ID
