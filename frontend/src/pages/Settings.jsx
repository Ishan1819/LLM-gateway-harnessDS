import { useState } from 'react'

import { Card, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import useApi from '../hooks/useApi'
import { useSession } from '../App'
import { api } from '../services/api'
import { currency } from '../lib/format'

function CopyField({ label, value, hint }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div>
      <p className="label">{label}</p>
      <div className="flex items-stretch gap-2">
        <code className="flex-1 min-w-0 truncate rounded-lg border border-hairline bg-page px-3 py-2 text-xs text-ink num">
          {value}
        </code>
        <button className="btn-ghost shrink-0" onClick={copy} type="button">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      {hint && <p className="mt-1.5 text-xs text-ink-muted">{hint}</p>}
    </div>
  )
}

export default function Settings() {
  const { organization } = useSession()
  const { data, error, loading, reload } = useApi(() => api.getKeys(), [])

  const [openaiKey, setOpenaiKey] = useState('')
  const [anthropicKey, setAnthropicKey] = useState('')
  const [budget, setBudget] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [formError, setFormError] = useState('')

  async function save(event) {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    setMessage('')
    try {
      const payload = {}
      if (openaiKey) payload.openai_api_key = openaiKey
      if (anthropicKey) payload.anthropic_api_key = anthropicKey
      if (budget !== '') payload.monthly_budget = Number(budget)
      await api.updateKeys(payload)
      setOpenaiKey('')
      setAnthropicKey('')
      setBudget('')
      setMessage('Settings saved.')
      await reload()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Spinner label="Loading settings" />
  if (error) return <ErrorNote message={error} onRetry={reload} />

  const proxyUrl = data.proxy_base_url || organization?.proxy_base_url || ''

  return (
    <>
      <PageHeader
        title="Settings"
        subtitle={`${organization?.name} · slug ${organization?.slug}`}
      />

      {message && (
        <div className="mb-4 rounded-lg border border-good/30 bg-good/[0.07] px-4 py-2.5 text-sm text-good">
          <span aria-hidden="true" className="mr-2">●</span>
          {message}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Card
          title="Provider API keys"
          subtitle="Your own keys. Encrypted at rest and never returned by the API."
        >
          <form onSubmit={save} className="space-y-4">
            <div>
              <label className="label" htmlFor="openai-key">OpenAI API key</label>
              <input
                id="openai-key"
                className="input"
                type="password"
                autoComplete="off"
                value={openaiKey}
                onChange={(e) => setOpenaiKey(e.target.value)}
                placeholder={data.openai ? `Currently ${data.openai}` : 'sk-…'}
              />
            </div>

            <div>
              <label className="label" htmlFor="anthropic-key">Anthropic API key</label>
              <input
                id="anthropic-key"
                className="input"
                type="password"
                autoComplete="off"
                value={anthropicKey}
                onChange={(e) => setAnthropicKey(e.target.value)}
                placeholder={data.anthropic ? `Currently ${data.anthropic}` : 'sk-ant-…'}
              />
            </div>

            <div>
              <label className="label" htmlFor="budget">Organization monthly budget (USD)</label>
              <input
                id="budget"
                className="input num"
                type="number"
                min="0"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                placeholder={String(data.monthly_budget || 0)}
              />
              <p className="mt-1.5 text-xs text-ink-muted">
                Currently {currency(data.monthly_budget, { decimals: 0 })}. Set to 0 for no
                org-wide limit.
              </p>
            </div>

            <ErrorNote message={formError} />

            <button className="btn-primary" type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Save settings'}
            </button>
          </form>
        </Card>

        <Card
          title="Connect your code"
          subtitle="Change the base URL. Nothing else in your code changes."
        >
          <div className="space-y-4">
            <CopyField
              label="Proxy base URL"
              value={proxyUrl}
              hint="Point both the OpenAI and Anthropic SDKs at this URL."
            />

            <div>
              <p className="label">Python — OpenAI SDK</p>
              <pre className="overflow-x-auto rounded-lg border border-hairline bg-page px-3 py-3 text-xs leading-relaxed text-ink-secondary">
{`from openai import OpenAI

client = OpenAI(
    base_url="${proxyUrl}",
    api_key="<your proxy key>",   # from the Users page
)

client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
)`}
              </pre>
            </div>

            <div>
              <p className="label">Python — Anthropic SDK</p>
              <pre className="overflow-x-auto rounded-lg border border-hairline bg-page px-3 py-3 text-xs leading-relaxed text-ink-secondary">
{`from anthropic import Anthropic

client = Anthropic(
    base_url="${proxyUrl}",
    api_key="<your proxy key>",
)

client.messages.create(
    model="claude-opus-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)`}
              </pre>
            </div>

            <p className="text-xs leading-relaxed text-ink-muted">
              Each user gets a unique proxy key so spend is attributed per person. Requests are
              rejected with HTTP 429 once a cap is reached.
            </p>
          </div>
        </Card>
      </div>
    </>
  )
}
