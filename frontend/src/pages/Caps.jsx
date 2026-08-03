import { useState } from 'react'

import { Card, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import CapEditor from '../components/CapEditor'
import UserTable from '../components/UserTable'
import { TeamTable } from '../components/TeamBreakdown'
import useApi from '../hooks/useApi'
import { api } from '../services/api'

export default function Caps() {
  const { data: users, error, loading, reload } = useApi(() => api.users(), [])
  const { data: teams, reload: reloadTeams } = useApi(() => api.teams(), [])

  const [editing, setEditing] = useState(null) // { kind, subject }
  const [selected, setSelected] = useState([])
  const [bulk, setBulk] = useState({ monthly_cap: '', daily_cap: '' })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [formError, setFormError] = useState('')

  async function saveCaps(payload) {
    setSaving(true)
    setFormError('')
    try {
      if (editing.kind === 'user') await api.updateUserCaps(editing.subject.id, payload)
      else await api.updateTeamCaps(editing.subject.id, payload)
      setEditing(null)
      setMessage(`Updated caps for ${editing.subject.name}.`)
      await Promise.all([reload(), reloadTeams()])
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function applyBulk(event) {
    event.preventDefault()
    if (!selected.length) return
    setSaving(true)
    setFormError('')
    try {
      const payload = { user_ids: selected }
      if (bulk.monthly_cap !== '') payload.monthly_cap = Number(bulk.monthly_cap)
      if (bulk.daily_cap !== '') payload.daily_cap = Number(bulk.daily_cap)
      const result = await api.bulkUpdateCaps(payload)
      setMessage(`Updated ${result.updated} users.`)
      setSelected([])
      setBulk({ monthly_cap: '', daily_cap: '' })
      await reload()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function setActive(isActive) {
    if (!selected.length) return
    setSaving(true)
    try {
      const result = await api.bulkUpdateCaps({ user_ids: selected, is_active: isActive })
      setMessage(`${isActive ? 'Enabled' : 'Disabled'} ${result.updated} users.`)
      setSelected([])
      await reload()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Spinner label="Loading caps" />
  if (error) return <ErrorNote message={error} onRetry={reload} />

  return (
    <>
      <PageHeader
        title="Cap management"
        subtitle="Set daily and monthly spending limits per user and per team"
      />

      {message && (
        <div className="mb-4 rounded-lg border border-good/30 bg-good/[0.07] px-4 py-2.5 text-sm text-good">
          <span aria-hidden="true" className="mr-2">●</span>
          {message}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        <Card
          title="Bulk update"
          subtitle={selected.length ? `${selected.length} selected` : 'Select users below'}
          className="xl:col-span-1"
        >
          <form onSubmit={applyBulk} className="space-y-3">
            <div>
              <label className="label" htmlFor="bulk-monthly">Monthly cap (USD)</label>
              <input
                id="bulk-monthly"
                className="input num"
                type="number"
                min="0"
                value={bulk.monthly_cap}
                onChange={(e) => setBulk({ ...bulk, monthly_cap: e.target.value })}
                placeholder="Leave blank to keep"
              />
            </div>
            <div>
              <label className="label" htmlFor="bulk-daily">Daily cap (USD)</label>
              <input
                id="bulk-daily"
                className="input num"
                type="number"
                min="0"
                value={bulk.daily_cap}
                onChange={(e) => setBulk({ ...bulk, daily_cap: e.target.value })}
                placeholder="Leave blank to keep"
              />
            </div>
            <button className="btn-primary w-full" type="submit" disabled={saving || !selected.length}>
              Apply to {selected.length || 0} users
            </button>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-ghost flex-1"
                disabled={saving || !selected.length}
                onClick={() => setActive(true)}
              >
                Enable
              </button>
              <button
                type="button"
                className="btn-ghost flex-1"
                disabled={saving || !selected.length}
                onClick={() => setActive(false)}
              >
                Disable
              </button>
            </div>
          </form>

          <div className="mt-4">
            <ErrorNote message={formError} />
          </div>
        </Card>

        <Card
          title={editing ? `Edit ${editing.kind} caps` : 'Single edit'}
          className="xl:col-span-2"
        >
          {editing ? (
            <CapEditor
              subject={editing.subject}
              kind={editing.kind}
              saving={saving}
              onSave={saveCaps}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <div className="py-8 text-center">
              <p className="text-sm text-ink-muted">
                Pick a team below to edit its caps, or select users for a bulk update.
              </p>
            </div>
          )}
        </Card>
      </div>

      <Card title="Team caps" className="mt-4" bodyClass="pb-2">
        <TeamTable
          teams={teams || []}
          onEdit={(team) => setEditing({ kind: 'team', subject: team })}
        />
      </Card>

      <Card
        title="User caps"
        subtitle="Select rows to bulk-update, or sort to find the heaviest users"
        className="mt-4"
        bodyClass="pb-2"
      >
        <UserTable users={users} selectable selected={selected} onSelect={setSelected} />
      </Card>
    </>
  )
}
