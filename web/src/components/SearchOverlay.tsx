import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '@/api/client'
import type { SearchResult } from '@/api/types'
import { useView } from '@/stores/view'
import { useWatchlist } from '@/stores/watchlist'
import { toProjectSymbol } from '@/utils/symbols'
import { SEARCH_LAYOUT_ID } from './SearchBar'

interface Props {
  onClose: () => void
  targetWatchlistId?: string
}

const SEARCH_LIMIT = 50
const PAGE_SIZE = 10

export function SearchOverlay({ onClose, targetWatchlistId }: Props) {
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), 220)
    return () => window.clearTimeout(id)
  }, [query])

  useEffect(() => {
    setPage(1)
  }, [debounced])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const { data, isFetching, isError, error } = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => api.search(debounced, SEARCH_LIMIT),
    enabled: debounced.length > 0,
  })

  const results = data?.results ?? []
  const totalPages = Math.ceil(results.length / PAGE_SIZE)
  const currentPage = Math.min(page, totalPages || 1)
  const visibleResults = results.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  )

  return (
    <motion.div
      key="search-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="搜索"
      className="fixed inset-0 z-50 flex flex-col safe-area-top safe-area-bottom"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
    >
      <motion.div
        className="absolute inset-0 bg-bg/85 backdrop-blur-md"
        onClick={onClose}
      />

      <div className="relative mx-auto mt-12 w-full max-w-2xl px-4 sm:mt-20">
        <motion.div
          layoutId={SEARCH_LAYOUT_ID}
          className="relative w-full"
          transition={{ type: 'spring', stiffness: 300, damping: 32 }}
        >
          <input
            autoFocus
            type="search"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="搜索股票 / ETF / 指数"
            aria-label="搜索"
            className="h-14 w-full rounded-xl border border-border bg-bg-card
                       pl-12 pr-12 text-lg text-ink
                       placeholder:text-ink-faint
                       shadow-2xl shadow-black/40
                       focus:outline-none focus:ring-2 focus:ring-accent"
          />
          <svg
            className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2
                       h-5 w-5 text-ink-faint"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭搜索"
            className="absolute right-3 top-1/2 grid h-9 w-9 -translate-y-1/2
                       place-items-center rounded-md text-ink-faint
                       hover:bg-bg-elev hover:text-ink
                       focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" strokeWidth={2.4}>
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </motion.div>

        <AnimatePresence mode="popLayout">
          {debounced.length > 0 && (
            <motion.section
              key="results"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 12 }}
              transition={{ duration: 0.18, delay: 0.05 }}
              className="mt-4 max-h-[70vh] overflow-y-auto rounded-xl
                         border border-border bg-bg-card shadow-xl
                         shadow-black/40"
            >
              {isFetching && (
                <div className="px-4 py-6 text-center text-sm text-ink-faint">
                  搜索中…
                </div>
              )}
              {isError && (
                <div className="px-4 py-6 text-center text-sm text-accent-down">
                  搜索失败：{(error as Error).message}
                </div>
              )}
              {data && results.length === 0 && !isFetching && (
                <div className="px-4 py-6 text-center text-sm text-ink-faint">
                  没有匹配 “{debounced}” 的结果
                </div>
              )}
              {data && results.length > 0 && (
                <>
                  <ul className="divide-y divide-border">
                    {visibleResults.map(r => (
                      <ResultRow
                        key={r.symbol}
                        result={r}
                        targetWatchlistId={targetWatchlistId}
                        onClose={onClose}
                      />
                    ))}
                  </ul>
                  {results.length > PAGE_SIZE && (
                    <div className="flex items-center justify-center gap-3 border-t
                                    border-border px-4 py-3 text-xs text-ink-dim">
                      <button
                        type="button"
                        onClick={() => setPage(p => Math.max(1, p - 1))}
                        disabled={currentPage === 1}
                        className="min-h-[32px] rounded-md border border-border
                                   bg-bg-elev px-3 hover:text-ink
                                   disabled:cursor-not-allowed disabled:opacity-45
                                   focus:outline-none focus:ring-2 focus:ring-accent"
                      >
                        ‹ 上一页
                      </button>
                      <span className="font-mono tabular-nums text-ink-faint">
                        第 {currentPage} / {totalPages} 页
                      </span>
                      <button
                        type="button"
                        onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                        disabled={currentPage === totalPages}
                        className="min-h-[32px] rounded-md border border-border
                                   bg-bg-elev px-3 hover:text-ink
                                   disabled:cursor-not-allowed disabled:opacity-45
                                   focus:outline-none focus:ring-2 focus:ring-accent"
                      >
                        下一页 ›
                      </button>
                    </div>
                  )}
                </>
              )}
            </motion.section>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}


function ResultRow({
  result,
  targetWatchlistId,
  onClose,
}: {
  result: SearchResult
  targetWatchlistId?: string
  onClose: () => void
}) {
  const goAsset = useView(s => s.goAsset)
  const [chooserOpen, setChooserOpen] = useState(false)
  const ids = useWatchlist(s => s.order)
  const watchlists = useWatchlist(s => s.watchlists)
  const addTicker = useWatchlist(s => s.addTicker)
  const symbol = toProjectSymbol(result.symbol)
  const targetWatchlist = targetWatchlistId ? watchlists[targetWatchlistId] : undefined
  const existsInTarget = !!targetWatchlist?.tickers.includes(symbol)

  const choose = (id: string) => {
    addTicker(id, symbol)
    setChooserOpen(false)
  }

  const addToTarget = () => {
    if (!targetWatchlistId || existsInTarget) return
    addTicker(targetWatchlistId, symbol)
  }

  return (
    <li className="relative">
      <div className="flex w-full items-center gap-3 px-4 py-3 transition-colors hover:bg-bg-elev">
        <button
          type="button"
          onClick={() => {
            goAsset(result.symbol)
            onClose()
          }}
          className="min-w-0 flex-1 text-left focus:outline-none focus:text-accent"
        >
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-sm font-semibold text-ink">
                {result.symbol}
              </span>
              <span className="truncate text-xs text-ink-dim">{result.name}</span>
            </div>
            <div className="mt-0.5 flex gap-2 text-[11px] text-ink-faint">
              {result.exchange && <span>{result.exchange}</span>}
              {result.type && <span>· {result.type}</span>}
            </div>
          </div>
        </button>
        {targetWatchlist ? (
          <button
            type="button"
            onClick={addToTarget}
            disabled={existsInTarget}
            className="shrink-0 rounded-md border border-border bg-bg-elev
                       px-2 py-1 text-xs text-ink-dim hover:text-ink
                       disabled:cursor-not-allowed disabled:opacity-45
                       focus:outline-none focus:ring-2 focus:ring-accent"
          >
            {existsInTarget ? '已添加' : '添加'}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => {
              setChooserOpen(o => !o)
            }}
            className="shrink-0 rounded-md border border-border bg-bg-elev
                       px-2 py-1 text-xs text-ink-dim hover:text-ink
                       focus:outline-none focus:ring-2 focus:ring-accent"
          >
            添加
          </button>
        )}
      </div>
      <AnimatePresence>
        {chooserOpen && !targetWatchlist && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            className="mx-4 mb-3 rounded-lg border border-border bg-bg-elev/70 p-2"
          >
            <div className="mb-2 text-[11px] uppercase tracking-wider text-ink-faint">
              添加到组合
            </div>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {ids.map(id => {
                const w = watchlists[id]
                if (!w) return null
                const exists = w.tickers.includes(symbol)
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => choose(id)}
                    disabled={exists}
                    className="flex min-h-[34px] items-center justify-between gap-2
                               rounded-md border border-border bg-bg-card px-2
                               text-left text-xs text-ink-dim hover:text-ink
                               disabled:cursor-not-allowed disabled:opacity-45
                               focus:outline-none focus:ring-2 focus:ring-accent"
                  >
                    <span className="truncate">{w.name}</span>
                    <span className="font-mono text-[11px] text-ink-faint">
                      {exists ? '已添加' : `${w.tickers.length}`}
                    </span>
                  </button>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  )
}
