import { Card, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import StatsCard from '../components/StatsCard'
import useApi from '../hooks/useApi'
import { api } from '../services/api'
import { compactNumber, currency, percent } from '../lib/format'

export default function Optimizer() {
  const { data, error, loading, reload } = useApi(() => api.optimizer(30), [])

  if (loading) return <Spinner label="Analysing usage" />
  if (error) return <ErrorNote message={error} onRetry={reload} />
  if (!data) return null

  const { opportunity, model_rightsizing: rightsizing, repeated_prompts: repeats } = data

  return (
    <>
      <PageHeader
        title="Cost Optimizer"
        subtitle={`Last 30 days · ${compactNumber(data.total_requests)} requests · ${currency(
          data.total_spend,
        )} spent`}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatsCard
          label="Total opportunity"
          value={currency(opportunity.total, { compact: true })}
          helper={`${percent(opportunity.pct_of_spend, 1)} of the last 30 days' spend`}
          accent="#8b5cf6"
        />
        <StatsCard
          label="Model right-sizing"
          value={currency(opportunity.model_rightsizing, { compact: true })}
          helper="Simpler requests moved one tier down"
        />
        <StatsCard
          label="Repeated prompts"
          value={currency(opportunity.repeated_prompts, { compact: true })}
          helper="Duplicate calls that caching could absorb"
        />
      </div>

      <div className="mt-4 rounded-card border border-s4/25 bg-s4/[0.06] px-5 py-4">
        <p className="text-sm text-ink-secondary">
          <span aria-hidden="true" className="mr-2 text-s4">◆</span>
          These are <span className="text-ink">estimates from observed usage</span>, not automatic
          changes. A model downgrade only holds if quality holds — validate on a sample before
          rolling it out.
        </p>
      </div>

      <Card
        title="Model right-sizing"
        subtitle="Requests below each model's own median context size — the simpler half of its traffic"
        className="mt-4"
        bodyClass="pb-2"
      >
        {rightsizing.length === 0 ? (
          <p className="py-8 text-center text-sm text-ink-muted">
            No downgrade candidates found — models look well matched to the work.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-hairline">
                  <th className="th">Current model</th>
                  <th className="th">Suggested</th>
                  <th className="th text-right">Candidates</th>
                  <th className="th text-right">Median prompt</th>
                  <th className="th text-right">Cost now</th>
                  <th className="th text-right">If switched</th>
                  <th className="th text-right">Saving</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline/60">
                {rightsizing.map((row) => (
                  <tr key={row.model} className="hover:bg-white/[0.02] transition-colors">
                    <td className="td font-medium text-ink">{row.model}</td>
                    <td className="td">
                      <span className="rounded-md bg-s4/15 px-2 py-0.5 text-xs font-medium text-s4">
                        {row.alternative}
                      </span>
                    </td>
                    <td className="td num text-right">
                      {compactNumber(row.candidate_requests)}
                      <span className="text-ink-muted"> / {compactNumber(row.total_requests)}</span>
                    </td>
                    <td className="td num text-right">
                      {compactNumber(row.median_prompt_tokens)}
                    </td>
                    <td className="td num text-right">{currency(row.current_cost)}</td>
                    <td className="td num text-right">{currency(row.projected_cost)}</td>
                    <td className="td num text-right font-medium text-good">
                      {currency(row.estimated_saving)}
                      <span className="ml-1.5 text-xs font-normal text-ink-muted">
                        {percent(row.saving_pct, 0)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="mt-4 grid gap-4 xl:grid-cols-2 items-start">
        <Card
          title="Repeated prompts"
          subtitle="Identical prompt sent three or more times by the same person"
          bodyClass="pb-2"
        >
          {repeats.length === 0 ? (
            <p className="py-8 text-center text-sm text-ink-muted">
              No significant prompt repetition detected.
            </p>
          ) : (
            <ul className="divide-y divide-hairline/60">
              {repeats.slice(0, 8).map((row) => (
                <li key={`${row.user_id}-${row.prompt_preview}`} className="py-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-sm font-medium text-ink truncate">{row.user}</span>
                    <span className="num shrink-0 text-sm text-good">
                      {currency(row.avoidable)}
                    </span>
                  </div>
                  <p className="mt-1 truncate font-mono text-xs text-ink-secondary">
                    “{row.prompt_preview}”
                  </p>
                  <p className="mt-1 text-[11px] text-ink-muted num">
                    {row.repeats}× · {row.models.join(', ')}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Team prompt efficiency"
          subtitle="Tailored guidance from each team's own traffic"
        >
          <ul className="space-y-4">
            {data.team_efficiency.map((team) => (
              <li key={team.team_id ?? team.team} className="rounded-lg bg-page/60 px-4 py-3.5">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-medium text-ink">{team.team}</span>
                  <span className="num text-xs text-ink-secondary">
                    {currency(team.cost_per_request, { decimals: 3 })}/request
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-muted num">
                  <span>avg prompt {compactNumber(team.avg_prompt_tokens)}</span>
                  <span>avg output {compactNumber(team.avg_completion_tokens)}</span>
                  <span>repeat rate {percent(team.repeat_rate_pct, 1)}</span>
                </div>
                <ul className="mt-2.5 space-y-1.5">
                  {team.guidance.map((line) => (
                    <li key={line} className="flex items-start gap-2 text-xs text-ink-secondary">
                      <span aria-hidden="true" className="mt-1 text-[8px] text-s4">
                        ●
                      </span>
                      {line}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  )
}
