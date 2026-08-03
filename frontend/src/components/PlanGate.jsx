import { Link } from 'react-router-dom'

import { COMPARISON, FEATURE_LABELS, PLAN_META, PLAN_ORDER, requiredPlanFor } from '../lib/plans'

function Tick({ value }) {
  if (value === true) {
    return (
      <span className="text-good" aria-label="Included">
        ●
      </span>
    )
  }
  if (value === false) {
    return (
      <span className="text-ink-muted/40" aria-label="Not included">
        —
      </span>
    )
  }
  return <span className="text-xs text-ink-secondary">{value}</span>
}

/** Side-by-side plan comparison, reused by the gate and the Plan page. */
export function PlanComparison({ currentPlan, highlight }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[540px]">
        <thead>
          <tr className="border-b border-hairline">
            <th className="th">Feature</th>
            {PLAN_ORDER.map((plan) => {
              const meta = PLAN_META[plan]
              const isCurrent = plan === currentPlan
              const isTarget = plan === highlight
              return (
                <th key={plan} className="th text-center">
                  <span
                    className="inline-flex flex-col items-center gap-0.5"
                    style={{ color: isTarget ? meta.accent : undefined }}
                  >
                    <span className="text-xs font-semibold">{meta.name}</span>
                    <span className="text-[10px] font-normal normal-case tracking-normal text-ink-muted">
                      {meta.price === 0 ? 'Free' : `$${meta.price}/mo`}
                    </span>
                    {isCurrent && (
                      <span className="rounded-full bg-white/[0.08] px-1.5 text-[9px] font-medium normal-case tracking-normal text-ink-secondary">
                        Current
                      </span>
                    )}
                  </span>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline/60">
          {COMPARISON.map((row) => (
            <tr key={row.label}>
              <td className="td text-ink-secondary">{row.label}</td>
              {PLAN_ORDER.map((plan) => (
                <td key={plan} className="td text-center">
                  <Tick value={row[plan]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Shown in place of a page the current plan doesn't include. Explains what the
 * feature does rather than just blocking, so the lock doubles as the pitch.
 */
export default function PlanGate({ feature, currentPlan = 'free', description, bullets = [] }) {
  const needed = requiredPlanFor(feature)
  const meta = PLAN_META[needed]

  return (
    <div className="mx-auto max-w-3xl">
      <div className="card px-8 py-10 text-center">
        <span
          className="mx-auto grid h-12 w-12 place-items-center rounded-xl text-lg"
          style={{ backgroundColor: `${meta.accent}1f`, color: meta.accent }}
          aria-hidden="true"
        >
          ◆
        </span>

        <h1 className="mt-5 text-xl font-semibold text-ink">
          {FEATURE_LABELS[feature] || 'This feature'} is a {meta.name} feature
        </h1>
        {description && (
          <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-ink-secondary">
            {description}
          </p>
        )}

        {bullets.length > 0 && (
          <ul className="mx-auto mt-6 max-w-md space-y-2.5 text-left">
            {bullets.map((line) => (
              <li key={line} className="flex items-start gap-3 text-sm text-ink-secondary">
                <span aria-hidden="true" className="mt-1 text-[9px]" style={{ color: meta.accent }}>
                  ●
                </span>
                {line}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-8 flex items-center justify-center gap-3">
          <Link to="/plan" className="btn-primary">
            Compare plans
          </Link>
          <Link to="/" className="btn-ghost">
            Back to overview
          </Link>
        </div>

        <p className="mt-5 text-xs text-ink-muted">
          You're on the {PLAN_META[currentPlan]?.name || 'Free'} plan.
        </p>
      </div>
    </div>
  )
}
