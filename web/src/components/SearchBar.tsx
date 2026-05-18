import { motion } from 'framer-motion'

interface Props {
  onActivate: () => void
  onSettingsClick: () => void
}

const SEARCH_LAYOUT_ID = 'search-bar'

export function SearchBar({ onActivate, onSettingsClick }: Props) {
  return (
    <div className="flex h-full min-h-tap w-full items-stretch gap-1.5">
      <motion.div
        layoutId={SEARCH_LAYOUT_ID}
        className="relative h-full flex-1 min-w-0"
        transition={{ type: 'spring', stiffness: 300, damping: 32 }}
      >
        <button
          type="button"
          onClick={onActivate}
          aria-label="打开搜索"
          className="flex h-full min-h-tap w-full items-center gap-2 rounded-lg border
                     border-border bg-bg-card py-2 pl-9 pr-3 text-left text-sm
                     text-ink-faint hover:bg-bg-elev hover:text-ink-dim
                     focus:outline-none focus:ring-2 focus:ring-accent"
        >
          搜索股票 / ETF / 指数
        </button>
        <svg
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2
                     h-4 w-4 text-ink-faint"
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      </motion.div>

      <button
        type="button"
        onClick={onSettingsClick}
        aria-label="设置"
        className="grid h-full min-h-tap w-tap shrink-0 place-items-center rounded-lg border
                   border-border bg-bg-card text-ink-dim
                   hover:bg-bg-elev hover:text-ink
                   focus:outline-none focus:ring-2 focus:ring-accent"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24"
             stroke="currentColor" strokeWidth={1.8}>
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
        </svg>
      </button>
    </div>
  )
}

export { SEARCH_LAYOUT_ID }
