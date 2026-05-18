import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  content: string
  label?: string
  className?: string
}

type TooltipPosition = { left: number; top: number; width: number }

const TOOLTIP_WIDTH = 256
const VIEWPORT_GAP = 12
const TRIGGER_GAP = 8

export function InfoTooltip({ content, label = '指标说明', className = '' }: Props) {
  const id = useId()
  const buttonRef = useRef<HTMLButtonElement>(null)
  const tooltipRef = useRef<HTMLSpanElement>(null)
  const [open, setOpen] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [position, setPosition] = useState<TooltipPosition | null>(null)

  const close = () => {
    setOpen(false)
    setPinned(false)
  }

  const updatePosition = () => {
    const button = buttonRef.current
    if (!button || typeof window === 'undefined') return
    const rect = button.getBoundingClientRect()
    const width = Math.min(TOOLTIP_WIDTH, window.innerWidth - VIEWPORT_GAP * 2)
    let left = rect.left + rect.width / 2 - width / 2
    left = Math.max(VIEWPORT_GAP, Math.min(left, window.innerWidth - width - VIEWPORT_GAP))

    const tooltipHeight = tooltipRef.current?.getBoundingClientRect().height ?? 0
    let top = rect.bottom + TRIGGER_GAP
    if (tooltipHeight > 0 && top + tooltipHeight > window.innerHeight - VIEWPORT_GAP) {
      top = rect.top - tooltipHeight - TRIGGER_GAP
    }
    top = Math.max(VIEWPORT_GAP, top)
    setPosition({ left, top, width })
  }

  useLayoutEffect(() => {
    if (!open) return
    updatePosition()
  }, [open, content])

  useEffect(() => {
    if (!open) return
    const onResize = () => updatePosition()
    const onScroll = () => updatePosition()
    const onPointerDown = (event: PointerEvent) => {
      if (!pinned) return
      const target = event.target as Node
      if (buttonRef.current?.contains(target) || tooltipRef.current?.contains(target)) return
      close()
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    window.addEventListener('resize', onResize)
    window.addEventListener('scroll', onScroll, true)
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('resize', onResize)
      window.removeEventListener('scroll', onScroll, true)
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, pinned])

  const tooltip = open && typeof document !== 'undefined'
    ? createPortal(
      <span
        id={id}
        ref={tooltipRef}
        role="tooltip"
        className="pointer-events-none fixed z-[70] whitespace-pre-line rounded-md
                   border border-border bg-bg-card px-3 py-2 text-left
                   text-[11px] font-normal leading-relaxed tracking-normal
                   text-ink shadow-xl shadow-black/30"
        style={{
          left: position?.left ?? VIEWPORT_GAP,
          top: position?.top ?? VIEWPORT_GAP,
          width: position?.width ?? TOOLTIP_WIDTH,
        }}
      >
        {content}
      </span>,
      document.body,
    )
    : null

  return (
    <span className={`inline-flex align-middle ${className}`}>
      <button
        ref={buttonRef}
        type="button"
        aria-label={`${label}：${content}`}
        aria-describedby={open ? id : undefined}
        title={content}
        onClick={event => {
          event.stopPropagation()
          const nextPinned = !pinned
          setPinned(nextPinned)
          setOpen(nextPinned)
        }}
        onMouseEnter={() => {
          if (!pinned) setOpen(true)
        }}
        onMouseLeave={() => {
          if (!pinned) setOpen(false)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          if (!pinned) setOpen(false)
        }}
        className="group grid h-4 w-4 place-items-center rounded-full
                   border border-border bg-bg-card text-[10px] font-semibold
                   leading-none text-ink-faint hover:border-accent hover:text-accent
                   focus:outline-none focus:ring-2 focus:ring-accent"
      >
        ?
      </button>
      {tooltip}
    </span>
  )
}
