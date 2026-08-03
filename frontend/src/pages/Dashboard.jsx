import { useEffect } from 'react'
import { Link } from 'react-router-dom'

import { Card, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import StatsCard from '../components/StatsCard'
import UsageChart from '../components/UsageChart'
import { TeamSpendChart, TeamTable } from '../components/TeamBreakdown'
import UserTable from '../components/UserTable'
import useApi from '../hooks/useApi'
import { useSession } from '../App'
import { api } from '../services/api'
import { compactNumber, currency, percent } from '../lib/format'

export default function Dashboard() {
  const { data, error, loading, reload } = useApi(() => api.dashboard(), [])
  const { setUnreadAlerts } = useSession()

  useEffect(() => {
    if (data) setUnreadAlerts(data.unread_alerts)
  }, [data, setUnreadAlerts])

  if (loading) return <Spinner label="Loading usage" />
  if (error) return <ErrorNote message={error} onRetry={reload} />
  if (!data) return null

  const { spend, counts, trend, teams, top_users: topUsers, models } = data
  const budget = data.org.monthly_budget
  const overBudget = budget > 0 && spend.projected_month > budget

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle={`${data.org.name} · month to date`}
        actions={
          <Link to="/savings" className="btn-ghost">
            Savings report
          </Link>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatsCard
          label="Spend today"
          value={currency(spend.today)}
          helper={`${compactNumber(counts.requests_today)} requests`}
          spark={trend.slice(-12)}
        />
        <StatsCard
          label="Spend this month"
          value={currency(spend.month)}
          helper={
            budget ? `${percent(data.budget_used_pct)} of ${currency(budget, { decimals: 0 })} budget` : 'No budget set'
          }
        />
        <StatsCard
          label="Projected month end"
          value={currency(spend.projected_month, { compact: true })}
          helper={
            budget
              ? overBudget
                ? `${currency(spend.projected_month - budget, { decimals: 0 })} over budget`
                : `${currency(budget - spend.projected_month, { decimals: 0 })} headroom`
              : 'At current run rate'
          }
        />
        <StatsCard
          label="Avoided by caps"
          value={currency(data.saved_this_month, { compact: true })}
          helper="Projected overshoot caps will block"
          accent="#10b981"
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3 items-start">
        <Card
          title="Daily spend"
          subtitle="Last 30 days, all teams"
          className="xl:col-span-2"
        >
          <UsageChart data={trend} height={272} />
        </Card>

        <Card title="Spend by team" subtitle="Month to date">
          <TeamSpendChart teams={teams} height={272} />
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3 items-start">
        <Card
          title="Team budgets"
          subtitle="Pace is month-end spend at the current run rate"
          className="xl:col-span-2"
          bodyClass="pb-2"
        >
          <TeamTable teams={teams} />
        </Card>

        <Card title="Spend by model" subtitle="Month to date">
          {models.length === 0 ? (
            <p className="py-8 text-center text-sm text-ink-muted">No usage recorded yet.</p>
          ) : (
            <ul className="space-y-3">
              {models.slice(0, 6).map((model) => {
                const share = models[0].spend ? (model.spend / models[0].spend) * 100 : 0
                return (
                  <li key={model.model}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-sm text-ink-secondary truncate">{model.model}</span>
                      <span className="num text-sm text-ink shrink-0">{currency(model.spend)}</span>
                    </div>
                    <div className="mt-1.5 h-1.5 w-full rounded-full bg-white/[0.07] overflow-hidden">
                      <div
                        className="h-full rounded-full bg-s1"
                        style={{ width: `${Math.max(2, share)}%` }}
                      />
                    </div>
                    <p className="mt-1 text-[11px] text-ink-muted num">
                      {compactNumber(model.requests)} requests · {compactNumber(model.tokens)} tokens
                    </p>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      </div>

      <Card
        title="Top spenders"
        subtitle="Highest month-to-date spend"
        className="mt-4"
        bodyClass="pb-2"
        actions={
          <Link to="/users" className="text-xs font-medium text-s1 hover:text-s1/80">
            View all {counts.total_users}
          </Link>
        }
      >
        <UserTable users={topUsers} />
      </Card>
    </>
  )
}
