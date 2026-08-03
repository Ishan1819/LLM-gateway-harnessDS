import { Card, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import PlanComparison from '../components/PlanComparison'
import useApi from '../hooks/useApi'
import { useSession } from '../App'
import { api } from '../services/api'
import { PLAN_META, PLAN_ORDER } from '../lib/plans'

function PlanCard({ plan, current }) {
  const meta = PLAN_META[plan.id]
  const isCurrent = plan.id === current

  return (
    <div
      className={`card flex flex-col px-5 py-5 ${isCurrent ? 'ring-1' : ''}`}
      style={isCurrent ? { '--tw-ring-color': meta.accent } : undefined}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold" style={{ color: meta.accent }}>
            {plan.name}
          </p>
          <p className="mt-0.5 text-xs text-ink-muted">{plan.tagline}</p>
        </div>
        {isCurrent && (
          <span className="rounded-full bg-white/[0.08] px-2 py-0.5 text-[10px] font-medium text-ink-secondary">
            Current
          </span>
        )}
      </div>

      <p className="mt-4 text-[26px] font-semibold leading-none text-ink">
        {plan.price_monthly === 0 ? 'Free' : `$${plan.price_monthly}`}
        {plan.price_monthly > 0 && (
          <span className="ml-1 text-xs font-normal text-ink-muted">/month</span>
        )}
      </p>

      <ul className="mt-5 flex-1 space-y-2">
        {plan.highlights.map((line) => (
          <li key={line} className="flex items-start gap-2.5 text-xs text-ink-secondary">
            <span aria-hidden="true" className="mt-1 text-[8px]" style={{ color: meta.accent }}>
              ●
            </span>
            {line}
          </li>
        ))}
      </ul>

      <button
        className={`mt-5 w-full ${isCurrent ? 'btn-ghost' : 'btn-primary'}`}
        disabled={isCurrent}
      >
        {isCurrent ? 'Current plan' : `Talk to sales`}
      </button>
    </div>
  )
}

export default function Plan() {
  const { organization } = useSession()
  const { data, error, loading, reload } = useApi(() => api.plan(), [])

  if (loading) return <Spinner label="Loading plans" />
  if (error) return <ErrorNote message={error} onRetry={reload} />
  if (!data) return null

  const current = data.current.id

  return (
    <>
      <PageHeader
        title="Plans & pricing"
        subtitle={`${organization?.name} is on the ${data.current.name} plan · ${data.usage.users} developers tracked`}
      />

      <div className="grid gap-4 lg:grid-cols-3 items-stretch">
        {PLAN_ORDER.map((id) => {
          const plan = data.plans.find((p) => p.id === id)
          return plan ? <PlanCard key={id} plan={plan} current={current} /> : null
        })}
      </div>

      <Card
        title="Full comparison"
        subtitle="Everything each plan includes"
        className="mt-4"
        bodyClass="pb-2"
      >
        <PlanComparison currentPlan={current} />
      </Card>

      <p className="mt-4 text-xs text-ink-muted">
        Plan changes are handled by sales in this build — there is no payment processor wired
        up. The tier is stored per organization and enforced by the API.
      </p>
    </>
  )
}
