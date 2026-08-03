export function currency(value, { compact = false, decimals } = {}) {
  const n = Number(value) || 0
  if (compact && Math.abs(n) >= 1000) {
    return `$${(n / 1000).toFixed(1)}K`
  }
  const places = decimals ?? (Math.abs(n) < 10 && n !== 0 ? 2 : Math.abs(n) < 1000 ? 2 : 0)
  return `$${n.toLocaleString('en-US', {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  })}`
}

export function compactNumber(value) {
  const n = Number(value) || 0
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString('en-US')
}

export function percent(value, decimals = 0) {
  return `${(Number(value) || 0).toFixed(decimals)}%`
}

export function shortDate(iso) {
  const d = new Date(`${iso}T00:00:00Z`)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

export function relativeTime(iso) {
  const then = new Date(iso)
  const diffMinutes = Math.round((Date.now() - then.getTime()) / 60000)
  if (diffMinutes < 1) return 'just now'
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const hours = Math.round(diffMinutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  return then.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/**
 * Utilization severity. Returns the status token plus a text label, because a
 * status colour must never carry meaning on its own.
 */
export function severity(pct) {
  if (pct >= 100) return { key: 'critical', label: 'Over cap', color: '#ef4444' }
  if (pct >= 80) return { key: 'critical', label: 'At risk', color: '#ef4444' }
  if (pct >= 60) return { key: 'warning', label: 'Watch', color: '#f59e0b' }
  return { key: 'good', label: 'Healthy', color: '#10b981' }
}

// Categorical series palette — validated against the #1e293b chart surface.
// Assigned in fixed order and never cycled; a 7th category folds into "Other".
export const SERIES = ['#3b82f6', '#ea580c', '#0d9488', '#8b5cf6', '#ec4899', '#65a30d']
export const OTHER = '#64748b'

export function seriesColor(index) {
  return index < SERIES.length ? SERIES[index] : OTHER
}
