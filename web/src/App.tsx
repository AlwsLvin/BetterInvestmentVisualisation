import { AnimatePresence } from 'framer-motion'
import { Home } from './pages/Home'
import { AssetDetail } from './pages/AssetDetail'
import { FxDetail } from './pages/FxDetail'
import { PortfolioDetail } from './pages/PortfolioDetail'
import { useView } from './stores/view'

export default function App() {
  const view = useView(s => s.view)
  return (
    <AnimatePresence mode="wait">
      {view.type === 'home' && <Home key={`home-${view.tab}`} />}
      {view.type === 'asset' && (
        <AssetDetail key={`asset-${view.symbol}`} symbol={view.symbol} />
      )}
      {view.type === 'fx' && (
        <FxDetail key={`fx-${view.symbol}-${view.inverse}`} symbol={view.symbol} inverse={view.inverse} />
      )}
      {view.type === 'portfolio' && <PortfolioDetail key="portfolio" />}
    </AnimatePresence>
  )
}
