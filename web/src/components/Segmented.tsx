import { motion } from 'framer-motion'

interface Option<T extends string> {
  value: T
  label: string
}

interface Props<T extends string> {
  options: readonly Option<T>[]
  value: T
  onChange: (v: T) => void
  className?: string
  size?: 'sm' | 'md'
}

export function Segmented<T extends string>({
  options, value, onChange, className = '', size = 'md',
}: Props<T>) {
  const idBase = `seg-${Math.random().toString(36).slice(2, 9)}`
  const padding = size === 'sm' ? 'px-3 py-1.5 text-xs' : 'px-4 py-2 text-sm'
  return (
    <div
      role="tablist"
      className={`relative inline-flex w-fit max-w-full self-start rounded-lg bg-bg-elev p-1 ${className}`}
    >
      {options.map(opt => {
        const active = opt.value === value
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={`relative z-10 ${padding} font-medium
                        rounded-md transition-colors min-h-[36px]
                        ${active ? 'text-white' : 'text-ink-dim hover:text-ink'}`}
          >
            {active && (
              <motion.span
                layoutId={idBase}
                className="absolute inset-0 -z-10 rounded-md bg-accent"
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              />
            )}
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
