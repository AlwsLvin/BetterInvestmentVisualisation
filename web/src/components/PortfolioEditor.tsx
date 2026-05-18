import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useWatchlist } from '@/stores/watchlist'
import { ConfirmDialog } from './ConfirmDialog'

type Mode =
  | { type: 'list' }
  | { type: 'detail'; id: string }

interface Props {
  onSearch?: (targetWatchlistId?: string) => void
}

export function PortfolioEditor({ onSearch }: Props) {
  const [mode, setMode] = useState<Mode>({ type: 'list' })
  const ids = useWatchlist(s => s.order)
  const watchlists = useWatchlist(s => s.watchlists)
  const activeId = useWatchlist(s => s.activeId)
  const createWatchlist = useWatchlist(s => s.createWatchlist)
  const setActiveWatchlist = useWatchlist(s => s.setActiveWatchlist)

  if (mode.type === 'detail') {
    const selected = watchlists[mode.id]
    if (!selected) {
      return (
        <PortfolioEditorList
          onOpen={id => setMode({ type: 'detail', id })}
          onSearch={onSearch}
        />
      )
    }
    return (
      <PortfolioEditorDetail
        id={mode.id}
        onBack={() => setMode({ type: 'list' })}
        onSearch={onSearch}
      />
    )
  }

  return (
    <PortfolioEditorList
      onOpen={id => setMode({ type: 'detail', id })}
      onCreate={() => {
        const id = createWatchlist()
        setMode({ type: 'detail', id })
      }}
      onSearch={onSearch}
      ids={ids}
      watchlists={watchlists}
      activeId={activeId}
      onActivate={setActiveWatchlist}
    />
  )
}

function PortfolioEditorList({
  ids,
  watchlists,
  activeId,
  onOpen,
  onActivate,
  onCreate,
  onSearch,
}: {
  ids?: string[]
  watchlists?: ReturnType<typeof useWatchlist.getState>['watchlists']
  activeId?: string
  onOpen: (id: string) => void
  onActivate?: (id: string) => void
  onCreate?: () => void
  onSearch?: (targetWatchlistId?: string) => void
}) {
  const storeIds = useWatchlist(s => s.order)
  const storeWatchlists = useWatchlist(s => s.watchlists)
  const storeActiveId = useWatchlist(s => s.activeId)
  const storeSetActive = useWatchlist(s => s.setActiveWatchlist)
  const storeCreate = useWatchlist(s => s.createWatchlist)
  const deleteWatchlist = useWatchlist(s => s.deleteWatchlist)
  const deleteWatchlists = useWatchlist(s => s.deleteWatchlists)
  const [multi, setMulti] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [confirm, setConfirm] = useState<null | {
    ids: string[]
    title: string
    message: string
    blocked?: boolean
  }>(null)

  const actualIds = ids ?? storeIds
  const actualWatchlists = watchlists ?? storeWatchlists
  const actualActiveId = activeId ?? storeActiveId
  const activate = onActivate ?? storeSetActive
  const create = onCreate ?? (() => {
    const id = storeCreate()
    onOpen(id)
  })
  const orderedIds = actualIds.filter(id => actualWatchlists[id])
  const selectedValidIds = selectedIds.filter(id => actualWatchlists[id])
  const selectedCount = selectedValidIds.length
  const onlyOneLeft = orderedIds.length <= 1

  const toggleSelected = (id: string) => {
    setSelectedIds(current =>
      current.includes(id)
        ? current.filter(item => item !== id)
        : [...current, id],
    )
  }

  const closeMulti = () => {
    setMulti(false)
    setSelectedIds([])
  }

  const requestSingleDelete = (id: string) => {
    const w = actualWatchlists[id]
    if (!w || onlyOneLeft) return
    setConfirm({
      ids: [id],
      title: '删除组合',
      message: `确认删除「${w.name}」？此操作不可撤销。`,
    })
  }

  const requestMultiDelete = () => {
    if (selectedCount === 0) {
      closeMulti()
      return
    }
    const first = actualWatchlists[selectedValidIds[0]]
    const blocked = orderedIds.length - selectedCount < 1
    setConfirm({
      ids: selectedValidIds,
      title: '删除组合',
      message: `确认删除「${first?.name ?? '组合'}」等 ${selectedCount} 个组合？此操作不可撤销。`,
      blocked,
    })
  }

  const confirmDelete = () => {
    if (!confirm || confirm.blocked) return
    if (confirm.ids.length === 1) deleteWatchlist(confirm.ids[0])
    else deleteWatchlists(confirm.ids)
    setConfirm(null)
    closeMulti()
  }

  useEffect(() => {
    if (!multi && selectedIds.length > 0) setSelectedIds([])
  }, [multi, selectedIds.length])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setMulti(true)}
            disabled={multi}
            className="min-h-[32px] rounded-md border border-border bg-bg-card
                       px-3 text-xs text-ink-dim hover:bg-bg-elev hover:text-ink
                       disabled:cursor-not-allowed disabled:opacity-45
                       focus:outline-none focus:ring-2 focus:ring-accent"
          >
            多选
          </button>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-ink-faint">
              组合列表
            </div>
            <div className="text-xs text-ink-dim">勾选后用于首页计算和回测</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <AnimatePresence initial={false}>
            {multi && selectedCount > 0 && (
              <motion.button
                key="delete-selected"
                type="button"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.14 }}
                onClick={requestMultiDelete}
                className="min-h-[32px] overflow-hidden whitespace-nowrap rounded-md
                           border border-accent-down bg-accent-down/10 px-3
                           text-xs font-medium text-accent-down
                           hover:bg-accent-down/20 focus:outline-none
                           focus:ring-2 focus:ring-accent-down"
              >
                删除（{selectedCount}）
              </motion.button>
            )}
          </AnimatePresence>
          {multi ? (
            <button
              type="button"
              onClick={requestMultiDelete}
              className="min-h-[32px] rounded-md border border-border bg-bg-card
                         px-3 text-xs text-ink-dim hover:bg-bg-elev hover:text-ink
                         focus:outline-none focus:ring-2 focus:ring-accent"
            >
              完成
            </button>
          ) : (
            <>
              {onSearch && (
                <button
                  type="button"
                  onClick={() => onSearch()}
                  className="min-h-[32px] rounded-md border border-border
                             bg-bg-card px-3 text-xs text-ink-dim
                             hover:bg-bg-elev hover:text-ink
                             focus:outline-none focus:ring-2 focus:ring-accent"
                >
                  搜索添加
                </button>
              )}
              <button
                type="button"
                onClick={create}
                className="min-h-[32px] rounded-md border border-border
                           bg-bg-card px-3 text-xs text-ink-dim
                           hover:bg-bg-elev hover:text-ink
                           focus:outline-none focus:ring-2 focus:ring-accent"
              >
                新建组合
              </button>
            </>
          )}
        </div>
      </div>

      <div className="grid gap-2">
        {orderedIds.map(id => {
          const w = actualWatchlists[id]
          if (!w) return null
          const active = id === actualActiveId
          const selected = selectedIds.includes(id)
          return (
            <motion.div key={id} layout className="flex items-center gap-2">
              <AnimatePresence initial={false}>
                {multi && (
                  <motion.div
                    key="checkbox"
                    initial={{ opacity: 0, width: 0 }}
                    animate={{ opacity: 1, width: 30 }}
                    exit={{ opacity: 0, width: 0 }}
                    transition={{ type: 'spring', stiffness: 360, damping: 34 }}
                    className="grid h-[44px] shrink-0 place-items-center overflow-hidden"
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleSelected(id)}
                      aria-label={`选择 ${w.name}`}
                      className="h-4 w-4 accent-accent"
                    />
                  </motion.div>
                )}
              </AnimatePresence>
              <motion.button
                type="button"
                layout
                onClick={() => multi ? toggleSelected(id) : onOpen(id)}
                aria-pressed={multi ? selected : undefined}
                className={`min-h-[44px] flex-1 rounded-md border px-3 text-left
                            transition-colors focus:outline-none focus:ring-2
                            focus:ring-accent
                            ${selected
                              ? 'border-accent bg-accent/20 text-ink'
                              : active
                                ? 'border-accent bg-accent/10 text-ink'
                                : 'border-border bg-bg-card text-ink-dim hover:bg-bg-elev hover:text-ink'}`}
              >
                <div className="truncate font-medium">{w.name}</div>
                <div className="mt-0.5 text-[11px] text-ink-faint">
                  {w.tickers.length} 个标的
                </div>
              </motion.button>
              <button
                type="button"
                onClick={() => activate(id)}
                aria-label={`使用 ${w.name}`}
                className={`grid h-[44px] w-[44px] shrink-0 place-items-center rounded-md
                            border focus:outline-none focus:ring-2 focus:ring-accent
                            ${active
                              ? 'border-accent bg-accent text-white'
                              : 'border-border bg-bg-card text-ink-dim hover:bg-bg-elev hover:text-ink'}`}
              >
                {active && (
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" strokeWidth={2.5}>
                    <path d="m5 13 4 4L19 7" />
                  </svg>
                )}
              </button>
              <AnimatePresence initial={false}>
                {!multi && (
                  <motion.button
                    key="delete"
                    type="button"
                    initial={{ opacity: 0, width: 0 }}
                    animate={{ opacity: 1, width: 44 }}
                    exit={{ opacity: 0, width: 0 }}
                    transition={{ duration: 0.14 }}
                    onClick={() => requestSingleDelete(id)}
                    disabled={onlyOneLeft}
                    title={onlyOneLeft ? '至少保留一个组合' : `删除 ${w.name}`}
                    aria-label={`删除 ${w.name}`}
                    className="grid h-[44px] shrink-0 place-items-center overflow-hidden
                               rounded-md border border-border bg-bg-card
                               text-ink-faint hover:bg-accent-down/10
                               hover:text-accent-down disabled:cursor-not-allowed
                               disabled:opacity-45 disabled:hover:bg-bg-card
                               disabled:hover:text-ink-faint focus:outline-none
                               focus:ring-2 focus:ring-accent-down"
                  >
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" strokeWidth={2.4}>
                      <path d="M6 6l12 12M18 6 6 18" />
                    </svg>
                  </motion.button>
                )}
              </AnimatePresence>
            </motion.div>
          )
        })}
      </div>

      <AnimatePresence>
        {confirm && (
          <ConfirmDialog
            title={confirm.title}
            message={confirm.message}
            confirmLabel="确认删除"
            confirmDisabled={confirm.blocked}
            disabledReason="至少保留一个组合"
            onCancel={() => setConfirm(null)}
            onConfirm={confirmDelete}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

function PortfolioEditorDetail({
  id,
  onBack,
  onSearch,
}: {
  id: string
  onBack: () => void
  onSearch?: (targetWatchlistId?: string) => void
}) {
  const watchlist = useWatchlist(s => s.watchlists[id])
  const renameWatchlist = useWatchlist(s => s.renameWatchlist)
  const removeTicker = useWatchlist(s => s.removeTicker)
  const [nameDraft, setNameDraft] = useState(watchlist.name)

  useEffect(() => setNameDraft(watchlist.name), [watchlist.name])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={onBack}
            aria-label="返回组合列表"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-md
                       border border-border bg-bg-card text-ink-dim
                       hover:bg-bg-elev hover:text-ink
                       focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" strokeWidth={2.2}>
              <path d="M15 18 9 12l6-6" />
            </svg>
          </button>
          <input
            value={nameDraft}
            onChange={e => {
              setNameDraft(e.target.value)
              renameWatchlist(id, e.target.value)
            }}
            onBlur={() => {
              const trimmed = nameDraft.trim()
              if (!trimmed) {
                setNameDraft(watchlist.name)
                return
              }
              renameWatchlist(id, trimmed)
            }}
            aria-label="组合名称"
            className="min-w-0 bg-transparent text-lg font-semibold text-ink
                       outline-none focus:text-accent sm:text-xl"
          />
        </div>
        {onSearch && (
          <button
            type="button"
            onClick={() => onSearch(id)}
            className="min-h-[36px] rounded-md border border-border bg-bg-card
                       px-3 text-sm text-ink-dim hover:bg-bg-elev hover:text-ink
                       focus:outline-none focus:ring-2 focus:ring-accent"
          >
            搜索添加
          </button>
        )}
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <AnimatePresence initial={false}>
          {watchlist.tickers.map(t => (
            <motion.div
              key={t}
              layout
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ duration: 0.12 }}
              className="flex min-h-[36px] items-center gap-2 rounded-md border
                         border-border bg-bg-card px-2"
            >
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-ink">
                {t}
              </span>
              <button
                type="button"
                onClick={() => removeTicker(id, t)}
                aria-label={`移除 ${t}`}
                className="grid h-6 w-6 shrink-0 place-items-center rounded
                           text-ink-faint hover:bg-bg-elev hover:text-accent-down
                           focus:outline-none focus:ring-2 focus:ring-accent"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" strokeWidth={2.4}>
                  <path d="M6 6l12 12M18 6 6 18" />
                </svg>
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {watchlist.tickers.length === 0 && (
        <div className="rounded-md border border-dashed border-border p-4
                        text-center text-xs text-ink-faint">
          用右上角搜索栏添加股票 / ETF / 指数
        </div>
      )}
    </div>
  )
}
