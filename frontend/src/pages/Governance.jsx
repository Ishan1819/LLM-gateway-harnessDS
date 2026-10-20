import { useEffect, useState } from 'react'

import { useSession } from '../App'
import { Badge, Card, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import StatsCard from '../components/StatsCard'
import useApi from '../hooks/useApi'
import { compactNumber, currency, percent } from '../lib/format'
import { api } from '../services/api'

const PROXY_KEY_STORAGE = 'acg_tester_proxy_key'
const TIER_LABEL = { 1: 'Simple', 2: 'Capable', 3: 'Frontier' }

function GovernedTester({ orgSlug, onSent }) {
  const [proxyKey, setProxyKey] = useState(() => localStorage.getItem(PROXY_KEY_STORAGE) || '')
  const [model, setModel] = useState('gpt-4o')
  const [content, setContent] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (proxyKey) localStorage.setItem(PROXY_KEY_STORAGE, proxyKey)
  }, [proxyKey])

  async function send(event) {
    event.preventDefault()
    if (!orgSlug || !proxyKey || !content.trim()) return
    setSending(true)
    setError('')
    try {
      const { body, headers } = await api.tryGoverned(orgSlug, proxyKey, {
        model,
        messages: [{ role: 'user', content }],
      })
      setResult({ body, headers })
      onSent?.()
    } catch (err) {
      setError(err.message)
      setResult(null)
    } finally {
      setSending(false)
    }
  }

  const h = result?.headers || {}
  const originalTokens = Number(h['x-governance-original-tokens'])
  const compressedTokens = Number(h['x-governance-compressed-tokens'])
  const reductionPct = Number(h['x-governance-token-reduction-pct'])
  const requestedModel = h['x-governance-requested-model']
  const routedModel = h['x-governance-routed-model']
  const tier = Number(h['x-governance-complexity-tier'])
  const savingsUsd = Number(h['x-governance-estimated-savings-usd'])
  const savingsPct = Number(h['x-governance-estimated-savings-pct'])

  return (
    <Card
      title="Try the governed endpoint"
      subtitle="Sends your text through real compression + routing. Every number below is measured from what you paste, not precomputed."
    >
      <form onSubmit={send} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="proxy-key">
              Proxy API key
            </label>
            <input
              id="proxy-key"
              className="input"
              type="password"
              autoComplete="off"
              value={proxyKey}
              onChange={(e) => setProxyKey(e.target.value)}
              placeholder="acg-…  (from the Users page)"
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="requested-model">
              Model you'd normally request
            </label>
            <input
              id="requested-model"
              className="input"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="gpt-4o"
              required
            />
          </div>
        </div>

        <div>
          <label className="label" htmlFor="content">
            Message content
          </label>
          <textarea
            id="content"
            className="input min-h-[160px] font-mono text-xs"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Paste a large or repetitive prompt — a log dump, RAG context, or conversation history — to see real compression in action."
            required
          />
        </div>

        <ErrorNote message={error} />

        <button className="btn-primary" type="submit" disabled={sending}>
          {sending ? 'Sending…' : 'Send through governed endpoint'}
        </button>
      </form>

      {result && (
        <div className="mt-6 border-t border-hairline pt-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatsCard
              label="Original tokens"
              value={compactNumber(originalTokens)}
              helper="measured with tiktoken"
            />
            <StatsCard
              label="Compressed tokens"
              value={compactNumber(compressedTokens)}
              helper={`${percent(reductionPct, 1)} reduction`}
              accent="#0d9488"
            />
            <StatsCard
              label="Estimated savings"
              value={currency(savingsUsd, { decimals: 4 })}
              helper={`${percent(savingsPct, 1)} of baseline cost`}
              accent="#10b981"
            />
            <StatsCard
              label="Complexity tier"
              value={TIER_LABEL[tier] || tier || '—'}
              helper={Number.isFinite(tier) ? `score-driven, tier ${tier}` : ''}
              accent="#8b5cf6"
            />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-ink-muted">Routed:</span>
            <Badge>{requestedModel}</Badge>
            <span aria-hidden="true" className="text-ink-muted">
              →
            </span>
            <Badge tone={routedModel === requestedModel ? 'neutral' : 'good'}>{routedModel}</Badge>
          </div>

          <details className="mt-4">
            <summary className="cursor-pointer text-xs text-ink-muted hover:text-ink">
              Raw response body
            </summary>
            <pre className="mt-2 overflow-x-auto rounded-lg border border-hairline bg-page px-3 py-3 text-xs text-ink-secondary">
              {JSON.stringify(result.body, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </Card>
  )
}

export default function Governance() {
  const { organization } = useSession()
  const { data, error, loading, reload } = useApi(() => api.governance('month'), [])

  return (
    <>
      <PageHeader
        title="AI Cost Governance"
        subtitle="Compression + model-routing savings, measured live per request — not hardcoded."
      />

      {loading && <Spinner label="Loading governance metrics" />}
      {error && <ErrorNote message={error} onRetry={reload} />}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatsCard
              label="Governed requests"
              value={compactNumber(data.total_requests)}
              helper="this month"
            />
            <StatsCard
              label="Token reduction"
              value={percent(data.token_reduction_pct, 1)}
              helper={`${compactNumber(data.original_tokens)} → ${compactNumber(data.compressed_tokens)} tokens`}
              accent="#0d9488"
            />
            <StatsCard
              label="Total saved"
              value={currency(data.total_saved_usd, { compact: true })}
              helper={`${percent(data.total_saved_pct, 1)} vs. ungoverned baseline`}
              accent="#10b981"
            />
            <StatsCard
              label="Optimized spend"
              value={currency(data.optimized_cost_usd, { compact: true })}
              helper={`vs. ${currency(data.original_estimated_cost_usd, { compact: true })} baseline`}
              accent="#3b82f6"
            />
          </div>

          <Card
            title="Model distribution"
            subtitle="Which model governed requests actually got routed to"
            className="mt-4"
            bodyClass="pb-2"
          >
            {data.model_distribution.length === 0 ? (
              <p className="py-8 text-center text-sm text-ink-muted">
                No governed requests yet — send one below to see it appear here.
              </p>
            ) : (
              <ul className="divide-y divide-hairline/60">
                {data.model_distribution.map((row) => (
                  <li key={row.model} className="flex items-center justify-between py-3">
                    <span className="text-sm font-medium text-ink">{row.model}</span>
                    <span className="num text-sm text-ink-secondary">
                      {compactNumber(row.requests)} requests
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}

      <div className="mt-4">
        <GovernedTester orgSlug={organization?.slug} onSent={reload} />
      </div>
    </>
  )
}
