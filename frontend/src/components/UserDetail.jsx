import { useEffect, useState } from 'react'

import { Meter, StatusPill } from './Primitives'
import { api } from '../services/api'
import { compactNumber, currency, percent } from '../lib/format'

/** Slide-over panel: full user detail plus their proxy API key, revealed on demand. */
export default function UserDetail({ user, onClose }) {
  const [key, setKey] = useState(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setKey(null)
    setCopied(false)
    setError('')
    if (!user) return
    api
      .revealKey(user.id)
      .then((data) => setKey(data.proxy_api_key))
      .catch((err) => setError(err.message))
  }, [user])

  if (!user) return null

  async function copy() {
    if (!key) return
    try {
      await navigator.clipboard.writeText(key)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        aria-label="Close"
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />
      <aside className="relative w-full max-w-md h-full bg-card border-l border-hairline/70 shadow-2xl overflow-y-auto">
        <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4 border-b border-hairline/60">
          <div>
            <h2 className="text-lg font-semibold text-ink">{user.name}</h2>
            <p className="text-sm text-ink-muted mt-0.5">{user.email}</p>
          </div>
          <button
            className="rounded-lg p-1.5 text-ink-muted hover:text-ink hover:bg-white/[0.06] transition-colors"
            onClick={onClose}
            aria-label="Close panel"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-5 space-y-6">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-page/60 px-3.5 py-3">
              <p className="text-xs text-ink-muted">Team</p>
              <p className="text-sm font-medium text-ink mt-0.5">{user.team}</p>
            </div>
            <div className="rounded-lg bg-page/60 px-3.5 py-3">
              <p className="text-xs text-ink-muted">Status</p>
              <p className="text-sm font-medium text-ink mt-0.5">
                {user.is_active ? 'Active' : 'Disabled'}
              </p>
            </div>
            <div className="rounded-lg bg-page/60 px-3.5 py-3">
              <p className="text-xs text-ink-muted">Spend (MTD)</p>
              <p className="num text-sm font-medium text-ink mt-0.5">{currency(user.spend)}</p>
            </div>
            <div className="rounded-lg bg-page/60 px-3.5 py-3">
              <p className="text-xs text-ink-muted">Tokens (MTD)</p>
              <p className="num text-sm font-medium text-ink mt-0.5">
                {compactNumber(user.tokens)}
              </p>
            </div>
          </div>

          {user.monthly_cap ? (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-xs font-medium text-ink-secondary">Pace against monthly cap</p>
                <StatusPill pct={user.pace_pct_of_cap} />
              </div>
              <Meter pct={user.pace_pct_of_cap} />
              <p className="mt-1.5 text-xs text-ink-muted num">
                {percent(user.pace_pct_of_cap)} of {currency(user.monthly_cap, { decimals: 0 })}{' '}
                monthly cap · {currency(user.daily_cap, { decimals: 2 })} daily cap
              </p>
            </div>
          ) : (
            <p className="text-sm text-ink-muted">No cap set for this user.</p>
          )}

          <div>
            <p className="label">Proxy API key</p>
            {error && <p className="text-xs text-critical">{error}</p>}
            {!error && (
              <>
                <div className="flex items-stretch gap-2">
                  <code className="flex-1 min-w-0 truncate rounded-lg border border-hairline bg-page px-3 py-2 text-xs text-ink num">
                    {key ?? 'Loading…'}
                  </code>
                  <button className="btn-ghost shrink-0" onClick={copy} disabled={!key}>
                    {copied ? 'Copied' : 'Copy'}
                  </button>
                </div>
                <p className="mt-1.5 text-xs text-ink-muted">
                  Use this as the <code className="text-ink-secondary">api_key</code> when pointing
                  the OpenAI or Anthropic SDK at the proxy.
                </p>
              </>
            )}
          </div>
        </div>
      </aside>
    </div>
  )
}
