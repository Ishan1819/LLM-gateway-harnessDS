/** Shared chart chrome: tokens and the tooltip shell every chart reuses. */

export const CHART = {
  surface: '#1e293b',
  grid: '#334155',
  axis: '#475569',
  muted: '#94a3b8',
  ink: '#f1f5f9',
  inkSecondary: '#cbd5e1',
}

export const axisTick = { fill: CHART.muted, fontSize: 11 }

export function TooltipShell({ title, rows }) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#0b1220]/95 px-3 py-2 shadow-xl backdrop-blur-sm">
      {title && <p className="text-[11px] font-medium text-ink-muted mb-1.5">{title}</p>}
      <div className="space-y-1">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center gap-3 text-xs">
            {row.color && (
              <span
                aria-hidden="true"
                className="h-2 w-2 rounded-full shrink-0"
                style={{ backgroundColor: row.color }}
              />
            )}
            <span className="text-ink-secondary">{row.label}</span>
            <span className="ml-auto num font-medium text-ink">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * Legend rendered as text tokens beside a colour key — never coloured text.
 * Always present when two or more series share a plot.
 */
export function Legend({ items }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-2 text-xs text-ink-secondary">
          <span
            aria-hidden="true"
            className="h-2 w-2 rounded-full shrink-0"
            style={{ backgroundColor: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  )
}
