import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { CHART, Legend, TooltipShell, axisTick } from '../components/ChartKit'
import PlanGate from '../components/PlanGate'
import { Card, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import StatsCard from '../components/StatsCard'
import UsageChart from '../components/UsageChart'
import { TeamTable } from '../components/TeamBreakdown'
import useApi from '../hooks/useApi'
import { useSession } from '../App'
import { api } from '../services/api'
import { FEATURES, hasFeature } from '../lib/plans'
import { OTHER, compactNumber, currency, seriesColor } from '../lib/format'

/**
 * Spend by model. Identity matters here, so categorical colour is doing real
 * work — assigned in fixed order, with a legend as the non-colour channel.
 * Past six models the tail folds into "Other" rather than inventing hues.
 */
function ModelChart({ models = [], height = 280 }) {
  const top = models.slice(0, 6)
  const tail = models.slice(6)
  const data = [...top]
  if (tail.length) {
    data.push({
      model: `Other (${tail.length})`,
      spend: tail.reduce((s, m) => s + m.spend, 0),
      tokens: tail.reduce((s, m) => s + m.tokens, 0),
      requests: tail.reduce((s, m) => s + m.requests, 0),
    })
  }

  // Colour follows the model, not its spend rank — assign by a stable
  // alphabetical slot so a model keeps its hue as the ranking shifts.
  const slots = new Map(
    top
      .map((m) => m.model)
      .sort((a, b) => a.localeCompare(b))
      .map((name, i) => [name, seriesColor(i)]),
  )
  const colored = data.map((m) => ({ ...m, fill: slots.get(m.model) ?? OTHER }))
  const max = Math.max(...colored.map((m) => m.spend), 0.01)

  return (
    <>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={[...colored].sort((a, b) => a.spend - b.spend)}
            layout="vertical"
            margin={{ top: 4, right: 64, bottom: 4, left: 4 }}
            barCategoryGap="32%"
          >
            <CartesianGrid stroke={CHART.grid} strokeWidth={1} horizontal={false} />
            <XAxis
              type="number"
              tick={axisTick}
              tickLine={false}
              axisLine={{ stroke: CHART.axis }}
              tickFormatter={(v) => currency(v, { compact: true, decimals: 0 })}
              domain={[0, Math.ceil(max * 1.18)]}
            />
            <YAxis
              type="category"
              dataKey="model"
              tick={{ ...axisTick, fill: CHART.inkSecondary }}
              tickLine={false}
              axisLine={false}
              width={140}
            />
            <Tooltip
              cursor={{ fill: 'rgba(255,255,255,0.04)' }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const m = payload[0].payload
                return (
                  <TooltipShell
                    title={m.model}
                    rows={[
                      { label: 'Spend', value: currency(m.spend), color: m.fill },
                      { label: 'Requests', value: compactNumber(m.requests) },
                      { label: 'Tokens', value: compactNumber(m.tokens) },
                    ]}
                  />
                )
              }}
            />
            <Bar
              dataKey="spend"
              radius={[0, 4, 4, 0]}
              maxBarSize={22}
              isAnimationActive={false}
              label={{
                position: 'right',
                formatter: (v) => currency(v, { decimals: v >= 1000 ? 0 : 2 }),
                fill: CHART.inkSecondary,
                fontSize: 11,
              }}
            >
              {[...colored]
                .sort((a, b) => a.spend - b.spend)
                .map((m) => (
                  <Cell key={m.model} fill={m.fill} />
                ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 pt-3 border-t border-hairline/60">
        <Legend items={colored.map((m) => ({ label: m.model, color: m.fill }))} />
      </div>
    </>
  )
}

export default function Savings() {
  const { organization } = useSession()
  const allowed = hasFeature(organization, FEATURES.SAVINGS)

  const { data, error, loading, reload } = useApi(
    () => (allowed ? api.savings() : Promise.resolve(null)),
    [allowed],
  )

  if (!allowed) {
    return (
      <PlanGate
        feature={FEATURES.SAVINGS}
        currentPlan={organization?.plan}
        description="Know where the month lands before it does — and which accounts are pulling it there."
        bullets={[
          'Month-end spend projection against your budget',
          'Like-for-like month-over-month comparison',
          'Spend broken down by model, with the expensive tail called out',
          'Accounts flagged for review when spend runs well above the team median',
        ]}
      />
    )
  }

  if (loading) return <Spinner label="Building savings report" />
  if (error) return <ErrorNote message={error} onRetry={reload} />
  if (!data) return null

  const overshoot = data.projected_month - data.budget

  return (
    <>
      <PageHeader
        title="Savings report"
        subtitle={`Day ${data.days_elapsed} of the month · projected against a ${currency(
          data.budget,
          { decimals: 0 },
        )} budget`}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatsCard
          label="Spend this month"
          value={currency(data.spend_this_month)}
          // No comparable window last month means no delta to show.
          delta={data.spend_last_month_same_window > 0 ? data.month_over_month_pct : null}
          deltaLabel="vs same days last month"
          helper={
            data.spend_last_month_same_window > 0
              ? undefined
              : 'No comparable window last month'
          }
        />
        <StatsCard
          label="Projected month end"
          value={currency(data.projected_month, { compact: true })}
          helper="At the current run rate"
        />
        <StatsCard
          label="Budget"
          value={currency(data.budget, { compact: true, decimals: 0 })}
          helper={
            data.over_budget
              ? `Projected ${currency(overshoot, { decimals: 0 })} over`
              : `${currency(data.remaining, { decimals: 0 })} remaining`
          }
          accent={data.over_budget ? '#ef4444' : '#10b981'}
        />
        <StatsCard
          label="Last month, full"
          value={currency(data.spend_last_month, { compact: true })}
          helper="Complete billing period"
        />
      </div>

      {data.over_budget && (
        <div className="mt-4 rounded-card border border-critical/30 bg-critical/[0.07] px-5 py-4">
          <p className="text-sm font-medium text-critical">
            <span aria-hidden="true" className="mr-2">■</span>
            On pace to exceed the monthly budget
          </p>
          <p className="mt-1.5 text-sm text-ink-secondary">
            At the current run rate this org lands at{' '}
            <span className="num text-ink">{currency(data.projected_month)}</span> against a{' '}
            <span className="num text-ink">{currency(data.budget, { decimals: 0 })}</span> budget —
            an overshoot of{' '}
            <span className="num text-ink">{currency(overshoot, { decimals: 0 })}</span>. Tighten
            caps on the teams below, or raise the budget in Settings.
          </p>
        </div>
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-3 items-start">
        <Card title="Daily spend" subtitle="Last 30 days" className="xl:col-span-2">
          <UsageChart data={data.trend} height={280} />
        </Card>

        <Card title="Spend by model" subtitle="Month to date">
          <ModelChart models={data.models} height={280} />
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3 items-start">
        <Card
          title="Team budgets"
          subtitle="Pace is month-end spend at the current run rate"
          className="xl:col-span-2"
          bodyClass="pb-2"
        >
          <TeamTable teams={data.teams} />
        </Card>

        <Card
          title="Flagged for review"
          subtitle="Spend well above the team median"
        >
          {data.flagged_waste.length === 0 ? (
            <p className="py-8 text-center text-sm text-ink-muted">
              Nothing unusual — spend is evenly distributed.
            </p>
          ) : (
            <ul className="space-y-3">
              {data.flagged_waste.map((row) => (
                <li key={row.user} className="rounded-lg bg-page/60 px-3.5 py-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-sm font-medium text-ink truncate">{row.user}</span>
                    <span className="num text-sm text-ink shrink-0">{currency(row.spend)}</span>
                  </div>
                  <p className="mt-1 text-[11px] text-ink-muted">
                    {row.team} · {compactNumber(row.tokens)} tokens
                  </p>
                  <p className="mt-1.5 text-xs text-ink-secondary">{row.reason}</p>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 text-[11px] leading-relaxed text-ink-muted">
            A heuristic, not a verdict — high spend can be legitimate. Use it to decide who is
            worth a conversation.
          </p>
        </Card>
      </div>
    </>
  )
}
