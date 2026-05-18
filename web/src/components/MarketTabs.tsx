export type TabKey = 'watchlist' | 'cn' | 'us' | 'hk' | 'fx'

interface Props {
  active: TabKey
  onChange: (k: TabKey) => void
}

const TABS: { key: TabKey; label: string }[] = [
  { key: 'watchlist', label: '自选' },
  { key: 'cn', label: '中国大盘' },
  { key: 'us', label: '美股' },
  { key: 'hk', label: '港股' },
  { key: 'fx', label: '外汇' },
]

export function MarketTabs({ active, onChange }: Props) {
  return (
    <div
      className="flex w-full gap-2 overflow-x-auto scrollbar-hide
                 snap-x snap-mandatory"
    >
      {TABS.map(t => {
        const isActive = active === t.key
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            aria-pressed={isActive}
            className={`snap-start flex-1 min-w-[80px] rounded-lg px-4 py-2
                        min-h-tap text-sm font-medium
                        transition-colors focus:outline-none
                        focus:ring-2 focus:ring-accent
                        ${isActive
                          ? 'bg-accent text-white'
                          : 'bg-bg-card text-ink-dim hover:bg-bg-elev hover:text-ink'}`}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}
