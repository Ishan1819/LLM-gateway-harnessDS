import { severity } from '../lib/format'

export function Card({ title, subtitle, actions, className = '', bodyClass = '', children }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 px-5 pt-5 pb-3">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={bodyClass || 'px-5 pb-5'}>{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="text-sm text-ink-muted mt-1">{subtitle}</p>}
      </div>
      {actions}
    </div>
  )
}

/**
 * Utilization meter. The fill carries severity; the track is a dim step of the
 * same ramp so state reads across the whole bar. Always rendered next to a
 * text label — colour never carries the meaning alone.
 */
export function Meter({ pct, className = '' }) {
  const state = severity(pct)
  return (
    <div className={`h-1.5 w-full rounded-full bg-white/[0.07] overflow-hidden ${className}`}>
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${Math.min(100, Math.max(0, pct))}%`, backgroundColor: state.color }}
      />
    </div>
  )
}

const STATUS_GLYPH = {
  good: '●',
  warning: '▲',
  critical: '■',
}

/** Status pill: icon + label + colour, so it survives colour-blind viewing. */
export function StatusPill({ pct }) {
  const state = severity(pct)
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium"
      style={{ color: state.color, backgroundColor: `${state.color}1f` }}
    >
      <span aria-hidden="true" className="text-[8px] leading-none">
        {STATUS_GLYPH[state.key]}
      </span>
      {state.label}
    </span>
  )
}

export function Badge({ children, tone = 'neutral' }) {
  const tones = {
    neutral: 'bg-white/[0.06] text-ink-secondary',
    good: 'bg-good/15 text-good',
    warning: 'bg-warning/15 text-warning',
    critical: 'bg-critical/15 text-critical',
  }
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function EmptyState({ title, hint }) {
  return (
    <div className="py-14 text-center">
      <p className="text-sm font-medium text-ink-secondary">{title}</p>
      {hint && <p className="text-xs text-ink-muted mt-1.5">{hint}</p>}
    </div>
  )
}

export function Spinner({ label = 'Loading' }) {
  return (
    <div className="flex items-center justify-center gap-3 py-20 text-sm text-ink-muted">
      <span className="h-4 w-4 rounded-full border-2 border-hairline border-t-s1 animate-spin" />
      {label}…
    </div>
  )
}

export function ErrorNote({ message, onRetry }) {
  if (!message) return null
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-critical/30 bg-critical/10 px-4 py-3">
      <p className="text-sm text-critical">
        <span aria-hidden="true" className="mr-2">■</span>
        {message}
      </p>
      {onRetry && (
        <button className="text-xs font-medium text-ink-secondary hover:text-ink" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}
