import { useEffect, useState } from 'react'

/** Inline cap editor used for both users and teams. */
export default function CapEditor({ subject, kind, onSave, onCancel, saving }) {
  const [monthly, setMonthly] = useState('')
  const [daily, setDaily] = useState('')
  const [active, setActive] = useState(true)

  useEffect(() => {
    setMonthly(String(subject?.monthly_cap ?? 0))
    setDaily(String(subject?.daily_cap ?? 0))
    setActive(subject?.is_active ?? true)
  }, [subject])

  if (!subject) return null

  function submit(event) {
    event.preventDefault()
    const payload = {
      monthly_cap: Number(monthly) || 0,
      daily_cap: Number(daily) || 0,
    }
    if (kind === 'user') payload.is_active = active
    onSave(payload)
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <p className="text-sm font-medium text-ink">{subject.name}</p>
        <p className="text-xs text-ink-muted mt-0.5">
          {kind === 'user' ? subject.email : `${subject.members ?? 0} members`}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="monthly-cap">
            Monthly cap (USD)
          </label>
          <input
            id="monthly-cap"
            className="input num"
            type="number"
            min="0"
            step="1"
            value={monthly}
            onChange={(e) => setMonthly(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="daily-cap">
            Daily cap (USD)
          </label>
          <input
            id="daily-cap"
            className="input num"
            type="number"
            min="0"
            step="0.5"
            value={daily}
            onChange={(e) => setDaily(e.target.value)}
          />
        </div>
      </div>

      <p className="text-xs text-ink-muted">
        Set a cap to 0 to leave it unlimited. Requests are rejected with HTTP 429 once a cap
        is reached.
      </p>

      {kind === 'user' && (
        <label className="flex items-center gap-2.5 text-sm text-ink-secondary cursor-pointer">
          <input
            type="checkbox"
            className="accent-s1"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          Account active
        </label>
      )}

      <div className="flex items-center gap-2 pt-1">
        <button className="btn-primary" type="submit" disabled={saving}>
          {saving ? 'Saving…' : 'Save caps'}
        </button>
        <button className="btn-ghost" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
