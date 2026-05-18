import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { MarketTabs } from '@/components/MarketTabs'
import { SearchBar } from '@/components/SearchBar'
import { SearchOverlay } from '@/components/SearchOverlay'
import { SettingsModal } from '@/components/SettingsModal'
import { MainPanel } from '@/components/MainPanel'
import { MiniIndexCard } from '@/components/MiniIndexCard'
import { useView } from '@/stores/view'

const MINI_INDICES = [
  { code: '^IXIC',     label: '纳斯达克' },
  { code: '^N225',     label: '日经 225' },
  { code: '000300.SS', label: '沪深 300' },
]

export function Home() {
  const tab = useView(s => s.view.type === 'home' ? s.view.tab : 'watchlist')
  const range = useView(s => s.homeRange)
  const setTab = useView(s => s.setHomeTab)
  const setRange = useView(s => s.setHomeRange)
  const goAsset = useView(s => s.goAsset)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchTargetId, setSearchTargetId] = useState<string | undefined>()
  const [settingsOpen, setSettingsOpen] = useState(false)

  const openSearch = (targetWatchlistId?: string) => {
    setSearchTargetId(targetWatchlistId)
    setSearchOpen(true)
  }

  const closeSearch = () => {
    setSearchOpen(false)
    setSearchTargetId(undefined)
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
    >
      <div
        className="grid min-h-screen w-full gap-3 p-3 safe-area-top safe-area-bottom
                   grid-cols-1
                   lg:h-screen lg:grid-cols-[minmax(0,4fr)_minmax(280px,1.5fr)]
                   lg:grid-rows-[auto_minmax(0,1fr)] lg:gap-4 lg:p-4"
      >
        <div className="lg:col-start-1 lg:row-start-1">
          <MarketTabs active={tab} onChange={setTab} />
        </div>

        <div className="lg:col-start-2 lg:row-start-1">
          <AnimatePresence initial={false}>
            {!searchOpen && (
              <SearchBar
                key="searchbar-idle"
                onActivate={() => openSearch()}
                onSettingsClick={() => setSettingsOpen(true)}
              />
            )}
          </AnimatePresence>
        </div>

        <div className="min-h-[60vh] lg:min-h-0 lg:col-start-1 lg:row-start-2">
          <MainPanel
            tab={tab}
            range={range}
            onRangeChange={setRange}
            onSearch={openSearch}
          />
        </div>

        <div className="grid grid-cols-3 gap-2
                        lg:col-start-2 lg:row-start-2
                        lg:grid-cols-1 lg:grid-rows-3 lg:gap-3">
          {MINI_INDICES.map(idx => (
            <MiniIndexCard
              key={idx.code}
              symbol={idx.code}
              label={idx.label}
              onClick={() => goAsset(idx.code)}
            />
          ))}
        </div>
      </div>

      <AnimatePresence>
        {searchOpen && (
          <SearchOverlay key="search-overlay"
                         targetWatchlistId={searchTargetId}
                         onClose={closeSearch} />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {settingsOpen && (
          <SettingsModal key="settings-modal"
                         onClose={() => setSettingsOpen(false)} />
        )}
      </AnimatePresence>
    </motion.div>
  )
}
