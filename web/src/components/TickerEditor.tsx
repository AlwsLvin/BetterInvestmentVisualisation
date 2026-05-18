import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

interface Props {
  tickers: string[]
  onAdd: (t: string) => void
  onRemove: (t: string) => void
}

export function TickerEditor({ tickers, onAdd, onRemove }: Props) {
  const [draft, setDraft] = useState('')

  const submit = () => {
    const v = draft.trim()
    if (v) onAdd(v)
    setDraft('')
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        <AnimatePresence initial={false}>
          {tickers.map(t => (
            <motion.span
              key={t}
              layout
              initial={{ opacity: 0, scale: 0.85 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.85 }}
              transition={{ duration: 0.15 }}
              className="inline-flex items-center gap-1 rounded-md border
                         border-border bg-bg-elev pl-2 pr-1 py-1 font-mono
                         text-xs text-ink"
            >
              {t}
              <button
                type="button"
                onClick={() => onRemove(t)}
                aria-label={`移除 ${t}`}
                className="grid h-5 w-5 place-items-center rounded
                           text-ink-faint hover:bg-bg-card hover:text-accent-down"
              >
                <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" strokeWidth={2.4}>
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
            </motion.span>
          ))}
        </AnimatePresence>
      </div>

      <div className="flex gap-2">
        <input
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submit()}
          placeholder="添加：AAPL.US / 0700.HK / 600519.SH"
          className="flex-1 rounded-md border border-border bg-bg-elev
                     px-3 py-2 font-mono text-sm text-ink min-h-[36px]
                     placeholder:text-ink-faint placeholder:font-sans
                     focus:outline-none focus:ring-2 focus:ring-accent"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!draft.trim()}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium
                     text-white min-h-[36px]
                     disabled:opacity-40 disabled:cursor-not-allowed
                     hover:brightness-110 focus:outline-none focus:ring-2
                     focus:ring-accent"
        >
          添加
        </button>
      </div>
    </div>
  )
}
