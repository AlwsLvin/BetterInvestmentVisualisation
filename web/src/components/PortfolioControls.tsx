import { Segmented } from './Segmented'
import type { Scheme, Style } from '@/api/types'
import type { Plan, PortfolioPrefs } from '@/stores/watchlist'

const STYLES = [
  { value: 'high_return',    label: '高回报' },
  { value: 'low_volatility', label: '低波动' },
] as const

const SCHEMES = [
  { value: 'linear',  label: '线性' },
  { value: 'softmax', label: '指数' },
  { value: 'power',   label: '幂次' },
] as const

const FREQ_OPTIONS = [
  { value: 'daily',       label: '每日' },
  { value: 'weekly:MON',  label: '每周一' },
  { value: 'monthly:1',   label: '每月 1 日' },
  { value: 'monthly:15',  label: '每月 15 日' },
  { value: 'every:30d',   label: '每 30 天' },
]

interface Props {
  prefs: PortfolioPrefs
  plan: Plan
  onPrefs: (p: Partial<PortfolioPrefs>) => void
  onPlan: (p: Plan) => void
}

export function PortfolioControls({ prefs, plan, onPrefs, onPlan }: Props) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[auto_auto_1fr]">
      <Field label="风格">
        <Segmented<Style>
          options={STYLES}
          value={prefs.style}
          onChange={v => onPrefs({ style: v })}
        />
      </Field>

      <Field label="分配方案">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented<Scheme>
            options={SCHEMES}
            value={prefs.scheme}
            onChange={v => onPrefs({ scheme: v })}
          />
          {prefs.scheme === 'softmax' && (
            <Slider
              label="τ"
              min={0.05} max={1.0} step={0.05}
              value={prefs.tau}
              onChange={v => onPrefs({ tau: v })}
            />
          )}
          {prefs.scheme === 'power' && (
            <Slider
              label="p"
              min={1} max={5} step={0.5}
              value={prefs.power}
              onChange={v => onPrefs({ power: v })}
            />
          )}
        </div>
      </Field>

      <Field label="定投">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2
                             text-ink-faint">$</span>
            <input
              type="number"
              min={1}
              step={50}
              value={plan.amount}
              onChange={e => onPlan({ ...plan, amount: Number(e.target.value) || 0 })}
              className="h-11 w-24 rounded-md border border-border bg-bg-elev pl-6 pr-2
                         font-mono text-sm text-ink
                         focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          <select
            value={plan.frequency}
            onChange={e => onPlan({ ...plan, frequency: e.target.value })}
            className="h-11 rounded-md border border-border bg-bg-elev px-2 text-sm
                       text-ink
                       focus:outline-none focus:ring-2 focus:ring-accent"
          >
            {FREQ_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </Field>
    </div>
  )
}


function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-wider text-ink-faint">
        {label}
      </span>
      {children}
    </div>
  )
}


function Slider({
  label, min, max, step, value, onChange,
}: {
  label: string; min: number; max: number; step: number
  value: number; onChange: (v: number) => void
}) {
  return (
    <div className="flex items-center gap-2 rounded-md bg-bg-elev px-3 py-1.5">
      <span className="font-mono text-xs text-ink-dim">{label}</span>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-20 accent-accent"
      />
      <span className="font-mono text-xs tabular-nums text-ink w-10">
        {value.toFixed(2)}
      </span>
    </div>
  )
}
