import { relativeTime } from '../lib/format'
import { EmptyState } from './Primitives'

const KIND = {
  limit_reached: { label: 'Limit reached', color: '#ef4444', glyph: '■' },
  warning_90pct: { label: '90% of cap', color: '#f59e0b', glyph: '▲' },
  warning_80pct: { label: '80% of cap', color: '#f59e0b', glyph: '▲' },
}

export default function AlertsList({ alerts = [], onMarkRead }) {
  if (!alerts.length) {
    return <EmptyState title="No alerts yet" hint="Warnings appear here once a user crosses 80% of a cap." />
  }

  return (
    <ul className="divide-y divide-hairline/60">
      {alerts.map((alert) => {
        const kind = KIND[alert.type] || { label: alert.type, color: '#94a3b8', glyph: '●' }
        return (
          <li
            key={alert.id}
            className={`flex items-start gap-4 px-5 py-3.5 transition-colors ${
              alert.is_read ? 'opacity-60' : 'hover:bg-white/[0.02]'
            }`}
          >
            <span
              aria-hidden="true"
              className="mt-1 text-[9px] leading-none shrink-0"
              style={{ color: kind.color }}
            >
              {kind.glyph}
            </span>

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium" style={{ color: kind.color }}>
                  {kind.label}
                </span>
                {!alert.is_read && (
                  <span className="rounded-full bg-s1/15 px-1.5 py-0.5 text-[10px] font-medium text-s1">
                    New
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-ink-secondary">{alert.message}</p>
            </div>

            <div className="flex items-center gap-3 shrink-0">
              <span className="text-xs text-ink-muted num">{relativeTime(alert.created_at)}</span>
              {!alert.is_read && onMarkRead && (
                <button
                  className="text-xs font-medium text-ink-muted hover:text-ink transition-colors"
                  onClick={() => onMarkRead(alert.id)}
                >
                  Mark read
                </button>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
