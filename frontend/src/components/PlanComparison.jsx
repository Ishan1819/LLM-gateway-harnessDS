import { COMPARISON, PLAN_META, PLAN_ORDER, formatPrice } from '../lib/plans'

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

/** Side-by-side plan comparison for the Plans & pricing page. */
export default function PlanComparison({ currentPlan }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[540px]">
        <thead>
          <tr className="border-b border-hairline">
            <th className="th">Feature</th>
            {PLAN_ORDER.map((plan) => {
              const meta = PLAN_META[plan]
              const isCurrent = plan === currentPlan
              return (
                <th key={plan} className="th text-center">
                  <span className="inline-flex flex-col items-center gap-0.5">
                    <span className="text-xs font-semibold" style={{ color: meta.accent }}>
                      {meta.name}
                    </span>
                    <span className="text-[10px] font-normal normal-case tracking-normal text-ink-muted">
                      {formatPrice(meta.price)}
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
