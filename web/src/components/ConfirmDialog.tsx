import { useEffect } from 'react'
import { motion } from 'framer-motion'

interface Props {
  title: string
  message: string
  confirmLabel?: string
  confirmDisabled?: boolean
  disabledReason?: string
  onCancel: () => void
  onConfirm: () => void
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = '确认',
  confirmDisabled = false,
  disabledReason,
  onCancel,
  onConfirm,
}: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel])

  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-[60] grid place-items-center px-4
                 safe-area-top safe-area-bottom"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.16 }}
    >
      <button
        type="button"
        aria-label="取消"
        className="absolute inset-0 bg-bg/80 backdrop-blur-sm"
        onClick={onCancel}
      />
      <motion.div
        initial={{ opacity: 0, y: 10, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10, scale: 0.98 }}
        transition={{ duration: 0.16 }}
        className="relative w-full max-w-sm rounded-lg border border-border
                   bg-bg-card p-4 shadow-2xl shadow-black/40"
      >
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-ink-dim">{message}</p>
        {confirmDisabled && disabledReason && (
          <div className="mt-3 rounded-md border border-accent-down/30
                          bg-accent-down/10 px-3 py-2 text-xs text-accent-down">
            {disabledReason}
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="min-h-[36px] rounded-md border border-border bg-bg-elev
                       px-3 text-sm text-ink-dim hover:text-ink
                       focus:outline-none focus:ring-2 focus:ring-accent"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={confirmDisabled}
            className="min-h-[36px] rounded-md border border-accent-down
                       bg-accent-down px-3 text-sm font-medium text-white
                       hover:bg-accent-down/90 disabled:cursor-not-allowed
                       disabled:opacity-45 focus:outline-none
                       focus:ring-2 focus:ring-accent-down"
          >
            {confirmLabel}
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}
