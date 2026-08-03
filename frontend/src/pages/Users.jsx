import { useState } from 'react'

import { Card, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import UserDetail from '../components/UserDetail'
import UserTable from '../components/UserTable'
import useApi from '../hooks/useApi'
import { api } from '../services/api'
import { currency } from '../lib/format'

function InviteForm({ teams, onCreated }) {
  const [form, setForm] = useState({ name: '', email: '', team_id: '', monthly_cap: '', daily_cap: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [created, setCreated] = useState(null)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const user = await api.createUser({
        name: form.name,
        email: form.email,
        team_id: form.team_id ? Number(form.team_id) : null,
        monthly_cap: Number(form.monthly_cap) || 0,
        daily_cap: Number(form.daily_cap) || 0,
      })
      setCreated(user)
      setForm({ name: '', email: '', team_id: '', monthly_cap: '', daily_cap: '' })
      onCreated()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-6 sm:items-end">
        <div className="sm:col-span-2">
          <label className="label" htmlFor="user-name">Name</label>
          <input
            id="user-name"
            className="input"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </div>
        <div className="sm:col-span-2">
          <label className="label" htmlFor="user-email">Email</label>
          <input
            id="user-email"
            className="input"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
          />
        </div>
        <div className="sm:col-span-2">
          <label className="label" htmlFor="user-team">Team</label>
          <select
            id="user-team"
            className="input"
            value={form.team_id}
            onChange={(e) => setForm({ ...form, team_id: e.target.value })}
          >
            <option value="">Unassigned</option>
            {teams.map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
              </option>
            ))}
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="label" htmlFor="user-monthly">Monthly cap (USD)</label>
          <input
            id="user-monthly"
            className="input num"
            type="number"
            min="0"
            value={form.monthly_cap}
            onChange={(e) => setForm({ ...form, monthly_cap: e.target.value })}
            placeholder="0 = unlimited"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="label" htmlFor="user-daily">Daily cap (USD)</label>
          <input
            id="user-daily"
            className="input num"
            type="number"
            min="0"
            value={form.daily_cap}
            onChange={(e) => setForm({ ...form, daily_cap: e.target.value })}
            placeholder="0 = unlimited"
          />
        </div>
        <div className="sm:col-span-2">
          <button className="btn-primary w-full" type="submit" disabled={busy}>
            {busy ? 'Creating…' : 'Create user'}
          </button>
        </div>
      </form>

      <div className="mt-3">
        <ErrorNote message={error} />
      </div>

      {created && (
        <div className="mt-4 rounded-lg border border-good/30 bg-good/[0.07] p-4">
          <p className="text-sm font-medium text-good">
            <span aria-hidden="true" className="mr-2">●</span>
            {created.name} created
          </p>
          <p className="mt-2 text-xs text-ink-secondary">
            Their proxy API key is shown once here — copy it now.
          </p>
          <code className="mt-2 block break-all rounded bg-page px-3 py-2 text-xs text-ink num">
            {created.proxy_api_key}
          </code>
        </div>
      )}
    </>
  )
}

export default function Users() {
  const { data: users, error, loading, reload } = useApi(() => api.users(), [])
  const { data: teams } = useApi(() => api.teams(), [])
  const [inviting, setInviting] = useState(false)
  const [detailUser, setDetailUser] = useState(null)

  if (loading) return <Spinner label="Loading users" />
  if (error) return <ErrorNote message={error} onRetry={reload} />

  const total = users.reduce((sum, u) => sum + u.spend, 0)
  const atRisk = users.filter((u) => u.monthly_cap && u.pace_pct_of_cap >= 80).length

  return (
    <>
      <PageHeader
        title="Users"
        subtitle={`${users.length} users · ${currency(total)} month to date · ${atRisk} at or near cap`}
        actions={
          <button className="btn-primary" onClick={() => setInviting((v) => !v)}>
            {inviting ? 'Cancel' : 'Add user'}
          </button>
        }
      />

      {inviting && (
        <Card
          title="Add a user"
          subtitle="Generates a unique proxy API key for attribution"
          className="mb-4"
        >
          <InviteForm teams={teams || []} onCreated={reload} />
        </Card>
      )}

      <Card
        title="All users"
        subtitle="Sort any column, or click a row to view details and their proxy key."
        bodyClass="pb-2"
      >
        <UserTable users={users} onRowClick={setDetailUser} />
      </Card>

      <UserDetail user={detailUser} onClose={() => setDetailUser(null)} />
    </>
  )
}
