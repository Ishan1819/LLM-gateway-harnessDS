import { useState } from 'react'

import { Card, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import PlanGate from '../components/PlanGate'
import { TeamSpendChart, TeamTable } from '../components/TeamBreakdown'
import CapEditor from '../components/CapEditor'
import useApi from '../hooks/useApi'
import { useSession } from '../App'
import { api } from '../services/api'
import { FEATURES, hasFeature } from '../lib/plans'
import { currency } from '../lib/format'

export default function Teams() {
  const { organization } = useSession()
  const allowed = hasFeature(organization, FEATURES.TEAM_CAPS)
  const { data: teams, error, loading, reload } = useApi(
    () => (allowed ? api.teams() : Promise.resolve([])),
    [allowed],
  )
  const [editing, setEditing] = useState(null)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [newTeam, setNewTeam] = useState({ name: '', monthly_cap: '', daily_cap: '' })

  async function saveCaps(payload) {
    setSaving(true)
    setFormError('')
    try {
      await api.updateTeamCaps(editing.id, payload)
      setEditing(null)
      await reload()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function createTeam(event) {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      await api.createTeam({
        name: newTeam.name,
        monthly_cap: Number(newTeam.monthly_cap) || 0,
        daily_cap: Number(newTeam.daily_cap) || 0,
      })
      setNewTeam({ name: '', monthly_cap: '', daily_cap: '' })
      setCreating(false)
      await reload()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (!allowed) {
    return (
      <PlanGate
        feature={FEATURES.TEAM_CAPS}
        currentPlan={organization?.plan}
        description="Group developers into teams and give each one its own budget, so a single team can't quietly consume the whole org's spend."
        bullets={[
          'Daily and monthly caps at the team level, enforced before requests leave',
          'Spend-per-team breakdown with pace against cap',
          'Bulk cap management across a whole team at once',
        ]}
      />
    )
  }

  if (loading) return <Spinner label="Loading teams" />
  if (error) return <ErrorNote message={error} onRetry={reload} />

  const total = teams.reduce((sum, t) => sum + t.spend, 0)

  return (
    <>
      <PageHeader
        title="Teams"
        subtitle={`${teams.length} teams · ${currency(total)} month to date`}
        actions={
          <button className="btn-primary" onClick={() => setCreating((v) => !v)}>
            {creating ? 'Cancel' : 'New team'}
          </button>
        }
      />

      {creating && (
        <Card title="Create a team" className="mb-4">
          <form onSubmit={createTeam} className="grid gap-3 sm:grid-cols-4 sm:items-end">
            <div className="sm:col-span-2">
              <label className="label" htmlFor="team-name">Team name</label>
              <input
                id="team-name"
                className="input"
                value={newTeam.name}
                onChange={(e) => setNewTeam({ ...newTeam, name: e.target.value })}
                placeholder="Platform"
                required
              />
            </div>
            <div>
              <label className="label" htmlFor="team-monthly">Monthly cap</label>
              <input
                id="team-monthly"
                className="input num"
                type="number"
                min="0"
                value={newTeam.monthly_cap}
                onChange={(e) => setNewTeam({ ...newTeam, monthly_cap: e.target.value })}
                placeholder="0"
              />
            </div>
            <div>
              <label className="label" htmlFor="team-daily">Daily cap</label>
              <input
                id="team-daily"
                className="input num"
                type="number"
                min="0"
                value={newTeam.daily_cap}
                onChange={(e) => setNewTeam({ ...newTeam, daily_cap: e.target.value })}
                placeholder="0"
              />
            </div>
            <div className="sm:col-span-4 flex items-center gap-3">
              <button className="btn-primary" type="submit" disabled={saving}>
                {saving ? 'Creating…' : 'Create team'}
              </button>
              <ErrorNote message={formError} />
            </div>
          </form>
        </Card>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Spend by team" subtitle="Month to date" className="xl:col-span-2">
          <TeamSpendChart teams={teams} height={260} />
        </Card>

        <Card title={editing ? 'Edit team caps' : 'Cap management'}>
          {editing ? (
            <>
              <CapEditor
                subject={editing}
                kind="team"
                saving={saving}
                onSave={saveCaps}
                onCancel={() => setEditing(null)}
              />
              <div className="mt-3">
                <ErrorNote message={formError} />
              </div>
            </>
          ) : (
            <p className="py-8 text-center text-sm text-ink-muted">
              Select <span className="text-ink-secondary">Edit caps</span> on a team to change its
              limits.
            </p>
          )}
        </Card>
      </div>

      <Card
        title="All teams"
        subtitle="Pace is month-end spend at the current run rate"
        className="mt-4"
        bodyClass="pb-2"
      >
        <TeamTable teams={teams} onEdit={setEditing} />
      </Card>
    </>
  )
}
