import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ThemeMode = 'auto' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

interface State {
  mode: ThemeMode
  resolved: ResolvedTheme
  setMode: (mode: ThemeMode) => void
  /** Re-resolve when "auto" and the system preference changes. */
  syncFromSystem: () => void
}

const _systemPrefersDark = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-color-scheme: dark)').matches

const _resolve = (mode: ThemeMode): ResolvedTheme =>
  mode === 'auto' ? (_systemPrefersDark() ? 'dark' : 'light') : mode

const _apply = (resolved: ResolvedTheme) => {
  if (typeof document === 'undefined') return
  const html = document.documentElement
  if (resolved === 'light') html.classList.add('light')
  else html.classList.remove('light')
}

export const useTheme = create<State>()(
  persist(
    set => ({
      mode: 'auto',
      resolved: _systemPrefersDark() ? 'dark' : 'light',

      setMode: mode => {
        const resolved = _resolve(mode)
        _apply(resolved)
        set({ mode, resolved })
      },

      syncFromSystem: () => set(s => {
        if (s.mode !== 'auto') return s
        const resolved = _resolve('auto')
        _apply(resolved)
        return { resolved }
      }),
    }),
    {
      name: 'bv-theme',
      version: 1,
      onRehydrateStorage: () => state => {
        if (!state) return
        const resolved = _resolve(state.mode)
        _apply(resolved)
        state.resolved = resolved
      },
    },
  ),
)

if (typeof window !== 'undefined') {
  window
    .matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', () => useTheme.getState().syncFromSystem())
}
