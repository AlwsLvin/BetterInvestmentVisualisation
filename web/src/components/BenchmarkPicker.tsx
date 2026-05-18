import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '@/api/client'

interface Props {
  value?: string
  onSelect: (symbol: string) => void
  onClear: () => void
}

export function BenchmarkPicker({ value, onSelect, onClear }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), 220)
    return () => window.clearTimeout(id)
  }, [query])

  const { data, isFetching } = useQuery({
    queryKey: ['benchmark-search', debounced],
    queryFn: () => api.search(debounced, 10),
    enabled: open && debounced.length > 0,
  })

  return (
    <div className="relative min-w-[220px] max-w-full flex-1 sm:flex-none">
      <div className="relative">
        <input
          value={query}
          onFocus={() => setOpen(true)}
          onChange={e => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          placeholder={value ? `基准：${value}` : '搜索基准标的'}
          aria-label="搜索基准标的"
          className="h-8 w-full rounded-md border border-border bg-bg-elev
                     pl-8 pr-8 text-xs text-ink placeholder:text-ink-faint
                     focus:outline-none focus:ring-2 focus:ring-accent"
        />
        <svg className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5
                        -translate-y-1/2 text-ink-faint"
             fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        {value && (
          <button
            type="button"
            onClick={() => {
              onClear()
              setQuery('')
              setDebounced('')
              setOpen(false)
            }}
            aria-label="清除基准"
            className="absolute right-1 top-1/2 grid h-6 w-6 -translate-y-1/2
                       place-items-center rounded text-ink-faint
                       hover:bg-bg-card hover:text-ink
                       focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" strokeWidth={2.4}>
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        )}
      </div>

      <AnimatePresence>
        {open && debounced.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-9 z-30 max-h-72 w-full overflow-y-auto
                       rounded-lg border border-border bg-bg-card shadow-xl"
          >
            {isFetching && (
              <div className="px-3 py-3 text-center text-xs text-ink-faint">
                搜索中...
              </div>
            )}
            {data?.results.map(r => (
              <button
                key={`${r.symbol}-${r.exchange}`}
                type="button"
                onClick={() => {
                  onSelect(r.symbol)
                  setQuery('')
                  setDebounced('')
                  setOpen(false)
                }}
                className="flex w-full flex-col border-t border-border px-3 py-2
                           text-left first:border-t-0 hover:bg-bg-elev
                           focus:outline-none focus:bg-bg-elev"
              >
                <span className="font-mono text-xs font-semibold text-ink">
                  {r.symbol}
                </span>
                <span className="truncate text-[11px] text-ink-faint">
                  {r.name || r.exchange}
                </span>
              </button>
            ))}
            {data && data.results.length === 0 && !isFetching && (
              <div className="px-3 py-3 text-center text-xs text-ink-faint">
                没有结果
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
