import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '@/api/client'
import type { AllocationLookbackDays, SettingsModel } from '@/api/types'
import { useTheme, type ThemeMode } from '@/stores/theme'

interface Props {
  onClose: () => void
}

const THEME_OPTIONS: { value: ThemeMode; label: string; hint: string }[] = [
  { value: 'auto',  label: '跟随系统', hint: '根据浏览器深色/浅色偏好' },
  { value: 'light', label: '亮色',     hint: '强制浅色主题' },
  { value: 'dark',  label: '暗色',     hint: '强制深色主题' },
]

const LOOKBACK_OPTIONS: { value: AllocationLookbackDays; label: string }[] = [
  { value: 30, label: '30天' },
  { value: 90, label: '90天' },
  { value: 180, label: '180天' },
  { value: 365, label: '1年' },
]

export function SettingsModal({ onClose }: Props) {
  const qc = useQueryClient()
  const themeMode = useTheme(s => s.mode)
  const setThemeMode = useTheme(s => s.setMode)
  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.getSettings(),
    staleTime: 0,
  })

  const [draft, setDraft] = useState<SettingsModel | null>(null)

  useEffect(() => {
    if (data && !draft) setDraft(data)
  }, [data, draft])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const save = useMutation({
    mutationFn: (next: SettingsModel) => api.putSettings(next),
    onSuccess: next => {
      qc.setQueryData(['settings'], next)
      qc.invalidateQueries({ queryKey: ['allocate'] })
      qc.invalidateQueries({ queryKey: ['rolling-backtest'] })
      qc.invalidateQueries({ queryKey: ['evaluate'] })
      onClose()
    },
  })

  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-label="设置"
      className="fixed inset-0 z-50 grid place-items-center p-4 safe-area-top safe-area-bottom"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
    >
      <div
        className="absolute inset-0 bg-bg/70 backdrop-blur-sm"
        onClick={onClose}
      />

      <motion.div
        className="relative w-full max-w-md rounded-xl border border-border
                   bg-bg-card p-5 shadow-2xl shadow-black/40"
        initial={{ scale: 0.94, y: 12 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.94, y: 12 }}
        transition={{ type: 'spring', stiffness: 300, damping: 28 }}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">设置</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="grid h-8 w-8 place-items-center rounded-md
                       text-ink-faint hover:bg-bg-elev hover:text-ink"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" strokeWidth={2.4}>
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        {(isLoading || !draft) ? (
          <div className="py-8 text-center text-sm text-ink-faint">加载中…</div>
        ) : (
          <div className="mt-4 flex flex-col gap-4">
            <Field label="主题">
              <div className="flex gap-2">
                {THEME_OPTIONS.map(opt => {
                  const active = opt.value === themeMode
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setThemeMode(opt.value)}
                      className={`flex-1 rounded-md border px-3 py-2 text-sm
                                  font-medium min-h-[40px]
                                  focus:outline-none focus:ring-2 focus:ring-accent
                                  ${active
                                    ? 'border-accent bg-accent text-white'
                                    : 'border-border bg-bg-elev text-ink-dim hover:text-ink'}`}
                    >
                      {opt.label}
                    </button>
                  )
                })}
              </div>
              <p className="mt-1 text-[11px] text-ink-faint">
                {THEME_OPTIONS.find(o => o.value === themeMode)?.hint}
              </p>
            </Field>

            <Field label="数据源">
              <select
                value={draft.data_source}
                onChange={e => setDraft({
                  ...draft, data_source: e.target.value as 'yfinance',
                })}
                className="w-full rounded-md border border-border bg-bg-elev
                           px-3 py-2 text-sm text-ink min-h-[40px]
                           focus:outline-none focus:ring-2 focus:ring-accent"
              >
                <option value="yfinance">yfinance（默认）</option>
              </select>
              <p className="mt-1 text-[11px] text-ink-faint">
                A 股 / akshare、香港 longport 等数据源待接入
              </p>
            </Field>

            <Field label="Beta 基准">
              <input
                type="text"
                value={draft.benchmark}
                onChange={e => setDraft({ ...draft, benchmark: e.target.value })}
                placeholder="^GSPC"
                className="w-full rounded-md border border-border bg-bg-elev
                           px-3 py-2 font-mono text-sm text-ink min-h-[40px]
                           focus:outline-none focus:ring-2 focus:ring-accent"
              />
              <p className="mt-1 text-[11px] text-ink-faint">
                历史默认值；当前组合会按持仓市场自动选择 Beta 基准
              </p>
            </Field>

            <Field label="模型回滚窗口">
              <div className="grid grid-cols-4 gap-2">
                {LOOKBACK_OPTIONS.map(opt => {
                  const active = draft.allocation_lookback_days === opt.value
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setDraft({
                        ...draft,
                        allocation_lookback_days: opt.value,
                      })}
                      className={`rounded-md border px-2 py-2 text-sm font-medium
                                  min-h-[40px] focus:outline-none
                                  focus:ring-2 focus:ring-accent
                                  ${active
                                    ? 'border-accent bg-accent text-white'
                                    : 'border-border bg-bg-elev text-ink-dim hover:text-ink'}`}
                    >
                      {opt.label}
                    </button>
                  )
                })}
              </div>
              <p className="mt-1 text-[11px] text-ink-faint">
                用于滚动 FAHP-FTOPSIS 投资比例训练，默认 1 年
              </p>
            </Field>

            {save.isError && (
              <div className="rounded-md border border-accent-down/40
                              bg-accent-down/10 p-2 text-xs text-accent-down">
                保存失败：{(save.error as Error).message}
              </div>
            )}

            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-border bg-bg-elev
                           px-4 py-2 text-sm text-ink-dim min-h-[40px]
                           hover:text-ink focus:outline-none focus:ring-2
                           focus:ring-accent"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => save.mutate(draft)}
                disabled={save.isPending}
                className="rounded-md bg-accent px-4 py-2 text-sm font-medium
                           text-white min-h-[40px] hover:brightness-110
                           disabled:opacity-50 focus:outline-none focus:ring-2
                           focus:ring-accent"
              >
                {save.isPending ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </motion.div>
  )
}


function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-wider text-ink-dim">
        {label}
      </span>
      {children}
    </label>
  )
}
