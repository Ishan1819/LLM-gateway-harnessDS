import { useEffect, useMemo, useState } from 'react'

import AlertsList from '../components/AlertsList'
import PlanGate from '../components/PlanGate'
import { Card, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import useApi from '../hooks/useApi'
import { useSession } from '../App'
import { api } from '../services/api'
import { FEATURES, hasFeature } from '../lib/plans'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'unread', label: 'Unread' },
  { key: 'limit_reached', label: 'Limit reached' },
  { key: 'warning_90pct', label: '90% warnings' },
  { key: 'warning_80pct', label: '80% warnings' },
]

export default function Alerts() {
  const { organization, setUnreadAlerts } = useSession()
  const allowed = hasFeature(organization, FEATURES.ALERTS)

  const { data: alerts, error, loading, reload, setData } = useApi(
    () => (allowed ? api.alerts(200) : Promise.resolve([])),
    [allowed],
  )
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    if (alerts) setUnreadAlerts(alerts.filter((a) => !a.is_read).length)
  }, [alerts, setUnreadAlerts])

  const visible = useMemo(() => {
    if (!alerts) return []
    if (filter === 'all') return alerts
    if (filter === 'unread') return alerts.filter((a) => !a.is_read)
    return alerts.filter((a) => a.type === filter)
  }, [alerts, filter])

  async function markRead(id) {
    setData((current) => current.map((a) => (a.id === id ? { ...a, is_read: true } : a)))
    try {
      await api.markAlertRead(id)
    } catch {
      reload()
    }
  }

  if (!allowed) {
    return (
      <PlanGate
        feature={FEATURES.ALERTS}
        currentPlan={organization?.plan}
        description="Get told the moment a developer or team crosses 80% of their budget — instead of finding out on the invoice."
        bullets={[
          'Automatic warnings at 80% and 90% of any cap',
          'Limit-reached events showing exactly who was blocked and when',
          'Filterable history across every user and team',
        ]}
      />
    )
  }

  if (loading) return <Spinner label="Loading alerts" />
  if (error) return <ErrorNote message={error} onRetry={reload} />

  const unread = alerts.filter((a) => !a.is_read).length

  return (
    <>
      <PageHeader
        title="Alerts"
        subtitle={`${alerts.length} events · ${unread} unread`}
      />

      {/* Filters sit in one row above the content. */}
      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((option) => (
          <button
            key={option.key}
            onClick={() => setFilter(option.key)}
            className={[
              'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
              filter === option.key
                ? 'bg-s1/15 text-s1'
                : 'bg-card text-ink-secondary hover:text-ink hover:bg-raised',
            ].join(' ')}
          >
            {option.label}
          </button>
        ))}
      </div>

      <Card bodyClass="pb-1">
        <AlertsList alerts={visible} onMarkRead={markRead} />
      </Card>
    </>
  )
}
