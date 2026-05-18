import type { Config } from 'tailwindcss'

// `<alpha-value>` placeholder lets Tailwind opacity modifiers work
// (e.g. `bg-accent/40`) — Tailwind substitutes the alpha at build time.
const rgb = (cssVar: string) => `rgb(var(${cssVar}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: rgb('--color-bg'),
          card:    rgb('--color-bg-card'),
          elev:    rgb('--color-bg-elev'),
        },
        ink: {
          DEFAULT: rgb('--color-ink'),
          dim:     rgb('--color-ink-dim'),
          faint:   rgb('--color-ink-faint'),
        },
        accent: {
          DEFAULT: rgb('--color-accent'),
          up:      rgb('--color-accent-up'),
          down:    rgb('--color-accent-down'),
        },
        border: {
          DEFAULT: rgb('--color-border'),
        },
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Helvetica Neue',
               'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'sans-serif'],
        mono: ['ui-monospace', 'SF Mono', 'Menlo', 'monospace'],
      },
      height: {
        tap: '44px',
      },
      width: {
        tap: '44px',
      },
      minHeight: {
        tap: '44px',
      },
      minWidth: {
        tap: '44px',
      },
    },
  },
  plugins: [],
} satisfies Config
