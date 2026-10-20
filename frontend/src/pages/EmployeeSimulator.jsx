import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Badge, Card, EmptyState, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import StatsCard from '../components/StatsCard'
import { CHART, TooltipShell, axisTick } from '../components/ChartKit'
import useApi from '../hooks/useApi'
import { currency } from '../lib/format'
import { api } from '../services/api'

// Ready-made scenarios, one per concept shown in the viva.
const PRESETS = [
  {
    id: 'spread',
    label: 'Load balancing',
    hint: 'All employees, 60 requests, 20 at a time — watch requests spread across gateway and mock-llm pods.',
    settings: { all: true, count: 60, concurrency: 20 },
  },
  {
    id: 'mutex',
    label: 'Mutual exclusion',
    hint: 'One employee, 20 requests at once on gpt-4-turbo — the per-user lock serialises them and the cap holds.',
    settings: { all: false, count: 20, concurrency: 20, model: 'gpt-4-turbo' },
  },
  {
    id: 'burst',
    label: 'Scale-out burst',
    hint: 'All employees, 300 requests, 50 at a time — sustained CPU for the autoscaler.',
    settings: { all: true, count: 300, concurrency: 50 },
  },
]

function PodChart({ title, counts }) {
  const rows = Object.entries(counts || {}).map(([pod, n]) => ({ pod, n }))
  return (
    <Card title={title} bodyClass="px-2 pb-4">
      {rows.length === 0 ? (
        <EmptyState title="No data" />
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="pod"
                tick={axisTick}
                tickFormatter={(p) => p.split('-').slice(-1)[0]}
                axisLine={{ stroke: CHART.axis }}
                tickLine={false}
              />
              <YAxis tick={axisTick} axisLine={false} tickLine={false} allowDecimals={false} width={36} />
              <Tooltip
                cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                content={({ active, payload }) =>
                  active && payload?.length ? (
                    <TooltipShell
                      title={payload[0].payload.pod}
                      rows={[{ label: 'Requests', value: payload[0].value, color: '#3b82f6' }]}
                    />
                  ) : null
                }
              />
              <Bar dataKey="n" fill="#3b82f6" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

function statusTone(code) {
  if (code === 200) return 'good'
  if (code === 429) return 'warning'
  return 'critical'
}

export default function EmployeeSimulator() {
  const { data: users, error: usersError, loading } = useApi(() => api.users(), [])
  const [selected, setSelected] = useState([])
  const [count, setCount] = useState(30)
  const [concurrency, setConcurrency] = useState(10)
  const [model, setModel] = useState('gpt-4o-mini')
  const [endpoint, setEndpoint] = useState('proxy')
  const [prompt, setPrompt] = useState('Summarize the quarterly churn report in three bullets.')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const activeUsers = useMemo(() => (users || []).filter((u) => u.is_active), [users])

  function applyPreset(preset) {
    const { all, count: c, concurrency: k, model: m = 'gpt-4o-mini' } = preset.settings
    setCount(c)
    setConcurrency(k)
    setModel(m)
    if (all) setSelected(activeUsers.map((u) => u.id))
    else if (activeUsers.length) setSelected([selected[0] ?? activeUsers[0].id])
  }

  function toggle(id) {
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))
  }

  async function run(event) {
    event.preventDefault()
    if (!selected.length) {
      setError('Pick at least one employee.')
      return
    }
    setRunning(true)
    setError('')
    try {
      setResult(
        await api.simulate({
          user_ids: selected,
          count: Number(count),
          concurrency: Number(concurrency),
          model,
          prompt,
          endpoint,
        }),
      )
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning(false)
    }
  }

  if (loading) return <Spinner label="Loading employees" />

  const ok = result?.status_counts?.['200'] || 0
  const blocked = result?.status_counts?.['429'] || 0
  const lockWaits = (result?.results || []).map((r) => r.lock_wait_ms).filter((x) => x != null)
  const maxLockWait = lockWaits.length ? Math.max(...lockWaits) : null

  return (
    <>
      <PageHeader
        title="Employee simulator"
        subtitle="Act as your employees: send their LLM requests through the gateway Service, exactly as their SDKs would."
      />
      <ErrorNote message={usersError} />

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Scenario presets" subtitle="One click per distributed-systems concept">
          <div className="space-y-2">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => applyPreset(p)}
                className="w-full rounded-lg border border-hairline bg-page px-4 py-3 text-left hover:border-s1/60"
              >
                <p className="text-sm font-medium text-ink">{p.label}</p>
                <p className="mt-0.5 text-xs text-ink-muted">{p.hint}</p>
              </button>
            ))}
          </div>
        </Card>

        <Card
          className="xl:col-span-2"
          title="Request settings"
          subtitle="Requests go to the gateway Service — each on a new connection, so Kubernetes picks a pod every time"
        >
          <form onSubmit={run} className="space-y-4">
            <div>
              <div className="flex items-center justify-between">
                <span className="label">Employees ({selected.length} selected)</span>
                <div className="flex gap-3 text-xs">
                  <button type="button" className="text-ink-muted hover:text-ink" onClick={() => setSelected(activeUsers.map((u) => u.id))}>
                    All
                  </button>
                  <button type="button" className="text-ink-muted hover:text-ink" onClick={() => setSelected([])}>
                    None
                  </button>
                </div>
              </div>
              <div className="mt-1 flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
                {activeUsers.map((u) => {
                  const on = selected.includes(u.id)
                  return (
                    <button
                      key={u.id}
                      type="button"
                      onClick={() => toggle(u.id)}
                      title={`${u.team} · ${currency(u.spend)} of ${u.monthly_cap ? currency(u.monthly_cap) : 'no cap'}`}
                      className={`rounded-md border px-2 py-1 text-xs ${
                        on ? 'border-s1 bg-s1/15 text-ink' : 'border-hairline text-ink-secondary hover:text-ink'
                      }`}
                    >
                      {u.name}
                      <span className="ml-1 text-ink-muted">· {u.team}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-4">
              <div>
                <label className="label" htmlFor="sim-count">Requests</label>
                <input id="sim-count" className="input" type="number" min="1" max="300" value={count}
                  onChange={(e) => setCount(e.target.value)} />
              </div>
              <div>
                <label className="label" htmlFor="sim-conc">Concurrency</label>
                <input id="sim-conc" className="input" type="number" min="1" max="50" value={concurrency}
                  onChange={(e) => setConcurrency(e.target.value)} />
              </div>
              <div>
                <label className="label" htmlFor="sim-model">Model</label>
                <select id="sim-model" className="input" value={model} onChange={(e) => setModel(e.target.value)}>
                  {['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo', 'claude-haiku-4-5', 'claude-sonnet-4-6', 'claude-opus-5'].map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label" htmlFor="sim-endpoint">Endpoint</label>
                <select id="sim-endpoint" className="input" value={endpoint} onChange={(e) => setEndpoint(e.target.value)}>
                  <option value="proxy">Proxy (passthrough)</option>
                  <option value="governed">Governed (compress + route)</option>
                </select>
              </div>
            </div>

            <div>
              <label className="label" htmlFor="sim-prompt">Prompt</label>
              <textarea id="sim-prompt" className="input min-h-[70px] text-xs" value={prompt}
                onChange={(e) => setPrompt(e.target.value)} />
            </div>

            <ErrorNote message={error} />
            <button className="btn-primary" type="submit" disabled={running}>
              {running ? 'Sending…' : `Send ${count} requests as ${selected.length || 0} employee(s)`}
            </button>
          </form>
        </Card>
      </div>

      {result && (
        <>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatsCard label="Succeeded" value={ok} helper={`of ${result.requested} · ${blocked} blocked by caps/locks`} accent="#10b981" />
            <StatsCard label="Throughput" value={`${result.throughput_rps} rps`} helper={`${(result.elapsed_ms / 1000).toFixed(1)}s total`} />
            <StatsCard label="Latency p50 / p95" value={`${result.latency_ms.p50 ?? '—'} ms`} helper={`p95 ${result.latency_ms.p95 ?? '—'} ms`} accent="#0d9488" />
            <StatsCard
              label="Max lock wait"
              value={maxLockWait == null ? '—' : `${maxLockWait.toFixed(0)} ms`}
              helper="time spent waiting for the employee's lock"
              accent="#ea580c"
            />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <PodChart title="Requests per gateway pod" counts={result.by_gateway_pod} />
            <PodChart title="Requests per mock-llm pod (RPC target)" counts={result.by_upstream_pod} />
          </div>

          <Card className="mt-4" title="Every request" subtitle={`Simulated from ${result.simulated_from}`} bodyClass="pb-2">
            <div className="max-h-[420px] overflow-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-card">
                  <tr className="text-left text-ink-muted">
                    <th className="px-5 py-2 font-medium">#</th>
                    <th className="py-2 font-medium">Employee</th>
                    <th className="py-2 font-medium">Status</th>
                    <th className="py-2 font-medium text-right">Latency</th>
                    <th className="py-2 font-medium text-right">Lock wait</th>
                    <th className="py-2 font-medium text-right">Lamport</th>
                    <th className="py-2 font-medium">Gateway pod</th>
                    <th className="py-2 pr-5 font-medium">LLM pod / error</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline/60">
                  {result.results.map((r) => (
                    <tr key={r.index}>
                      <td className="px-5 py-1.5 num text-ink-muted">{r.index + 1}</td>
                      <td className="py-1.5 text-ink-secondary">{r.user}</td>
                      <td className="py-1.5"><Badge tone={statusTone(r.status)}>{r.status || 'ERR'}</Badge></td>
                      <td className="py-1.5 num text-right text-ink-secondary">{r.latency_ms} ms</td>
                      <td className="py-1.5 num text-right text-ink-secondary">
                        {r.lock_wait_ms == null ? '—' : `${r.lock_wait_ms.toFixed(0)} ms`}
                      </td>
                      <td className="py-1.5 num text-right text-ink-secondary">{r.lamport ?? '—'}</td>
                      <td className="py-1.5 font-mono text-ink-muted">{r.gateway_pod || '—'}</td>
                      <td className="py-1.5 pr-5 font-mono text-ink-muted">{r.error || r.upstream_pod || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </>
  )
}
