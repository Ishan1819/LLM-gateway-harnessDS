import { useEffect, useRef, useState } from 'react'

import { Badge, Card, EmptyState, ErrorNote, PageHeader, Spinner } from '../components/Primitives'
import StatsCard from '../components/StatsCard'
import { compactNumber, currency } from '../lib/format'
import { api } from '../services/api'

const POLL_MS = 2000

const ROLE_META = {
  gateway: { label: 'Gateway', concept: 'Stateless API pods behind a Service · scaled by HPA', accent: '#3b82f6' },
  'usage-worker': {
    label: 'Usage workers',
    concept: 'Consumer group on the Redis Stream · message-oriented communication',
    accent: '#0d9488',
  },
  'alert-worker': {
    label: 'Alert workers',
    concept: 'Lease-based leader election · only the leader scans caps',
    accent: '#8b5cf6',
  },
}

function age(seconds) {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

function NodeCard({ node, isLeader, onStop, stopping }) {
  const now = Date.now() / 1000
  const lastSeen = now - Number(node.last_seen || now)
  const role = node.role
  return (
    <div
      className={`rounded-lg border px-4 py-3 ${
        isLeader ? 'border-[#8b5cf6]/60 bg-[#8b5cf6]/10' : 'border-hairline bg-page'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-mono text-xs text-ink break-all">{node.pod}</p>
        {isLeader && <Badge tone="good">★ leader · term {node.term}</Badge>}
        {role === 'alert-worker' && !isLeader && <Badge>follower</Badge>}
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        <dt className="text-ink-muted">Up</dt>
        <dd className="num text-ink-secondary text-right">{age(now - Number(node.started_at || now))}</dd>
        <dt className="text-ink-muted">Heartbeat</dt>
        <dd className="num text-ink-secondary text-right">{age(lastSeen)} ago</dd>
        {node.lamport !== undefined && (
          <>
            <dt className="text-ink-muted">Lamport clock</dt>
            <dd className="num text-ink-secondary text-right">{node.lamport}</dd>
          </>
        )}
        {role === 'gateway' && (
          <>
            <dt className="text-ink-muted">Requests served</dt>
            <dd className="num text-ink-secondary text-right">{compactNumber(node.requests)}</dd>
          </>
        )}
        {role === 'usage-worker' && (
          <>
            <dt className="text-ink-muted">Persisted</dt>
            <dd className="num text-ink-secondary text-right">{compactNumber(node.processed)}</dd>
            <dt className="text-ink-muted">Reclaimed / dupes</dt>
            <dd className="num text-ink-secondary text-right">
              {node.reclaimed} / {node.duplicates}
            </dd>
          </>
        )}
        {role === 'alert-worker' && (
          <>
            <dt className="text-ink-muted">Scans / alerts</dt>
            <dd className="num text-ink-secondary text-right">
              {node.scans} / {node.alerts_created}
            </dd>
          </>
        )}
      </dl>
      {onStop && (
        <button
          className="mt-3 w-full rounded-md border border-critical/40 bg-critical/10 px-2 py-1 text-[11px] font-medium text-critical hover:bg-critical/20 disabled:cursor-not-allowed disabled:opacity-50"
          onClick={() => onStop(node)}
          disabled={stopping}
        >
          {stopping ? 'Crashed · waiting for restart…' : '⏻ Turn off (simulate crash)'}
        </button>
      )}
    </div>
  )
}

export default function Cluster() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [paused, setPaused] = useState(false)
  // pod -> started_at when it was stopped; cleared once the pod restarts.
  const [stopping, setStopping] = useState({})
  const timer = useRef(null)

  async function load() {
    try {
      setData(await api.clusterStatus())
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
    if (paused) return undefined
    timer.current = setInterval(load, POLL_MS)
    return () => clearInterval(timer.current)
  }, [paused])

  async function reset() {
    await api.resetClusterStats()
    load()
  }

  async function stopNode(node) {
    try {
      await api.stopNode(node.pod)
      setStopping((s) => ({ ...s, [node.pod]: node.started_at }))
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!data && !error) return <Spinner label="Reading cluster state" />

  const nodes = data?.nodes || []
  const byRole = (role) => nodes.filter((n) => n.role === role)
  const leaderPod = data?.leader?.leader
  const stream = data?.stream
  const locks = data?.locks || {}

  return (
    <>
      <PageHeader
        title="Distributed cluster"
        subtitle={`Live view of every pod, refreshed every ${POLL_MS / 1000}s · this page was served by ${
          data?.served_by || '—'
        }`}
        actions={
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={() => setPaused((p) => !p)}>
              {paused ? '▶ Resume' : '❚❚ Pause'}
            </button>
            <button className="btn-ghost" onClick={reset}>
              Reset counters
            </button>
          </div>
        }
      />

      <ErrorNote message={error} onRetry={load} />

      {data && !data.redis && (
        <Card title="Single-process mode" className="mb-4">
          <p className="text-sm text-ink-secondary">
            Redis is not configured, so this gateway runs alone and writes usage synchronously. Deploy with
            docker compose or Kubernetes (scripts/deploy.ps1) to see the distributed system.
          </p>
        </Card>
      )}

      {data?.redis && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatsCard
              label="Live pods"
              value={nodes.length}
              helper={`${byRole('gateway').length} gateway · ${byRole('usage-worker').length} usage · ${
                byRole('alert-worker').length
              } alert`}
            />
            <StatsCard
              label="Queue backlog"
              value={compactNumber((stream?.lag ?? 0) + (stream?.pending ?? 0))}
              helper={`${stream?.lag ?? 0} undelivered · ${stream?.pending ?? 0} unacked`}
              accent="#0d9488"
            />
            <StatsCard
              label="Alert leader"
              value={leaderPod ? leaderPod.split('-').slice(-1)[0] : 'none'}
              helper={leaderPod ? `term ${data.leader.term} · lease ${data.leader.ttl_ms}ms` : 'election pending'}
              accent="#8b5cf6"
            />
            <StatsCard
              label="Lock acquisitions"
              value={compactNumber(locks.acquired || 0)}
              helper={`${locks.contended || 0} had to wait · ${locks.timeouts || 0} timed out`}
              accent="#ea580c"
            />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            {['gateway', 'usage-worker', 'alert-worker'].map((role) => (
              <Card key={role} title={ROLE_META[role].label} subtitle={ROLE_META[role].concept}>
                {byRole(role).length === 0 ? (
                  <EmptyState title="No live pods" hint="Heartbeats expire 10s after a pod stops." />
                ) : (
                  <div className="space-y-2">
                    {byRole(role).map((n) => (
                      <NodeCard
                        key={n.pod}
                        node={n}
                        isLeader={role === 'alert-worker' && n.pod === leaderPod}
                        onStop={role === 'alert-worker' ? stopNode : undefined}
                        stopping={stopping[n.pod] !== undefined && stopping[n.pod] === n.started_at}
                      />
                    ))}
                  </div>
                )}
              </Card>
            ))}
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <Card
              title="Message queue"
              subtitle={`Redis Stream ${stream?.name} · group ${stream?.group}`}
            >
              <dl className="grid grid-cols-2 gap-y-2 text-sm">
                <dt className="text-ink-muted">Events in stream</dt>
                <dd className="num text-right text-ink">{compactNumber(stream?.length)}</dd>
                <dt className="text-ink-muted">Not yet delivered</dt>
                <dd className="num text-right text-ink">{stream?.lag ?? '—'}</dd>
                <dt className="text-ink-muted">Delivered, not acked</dt>
                <dd className="num text-right text-ink">{stream?.pending ?? 0}</dd>
              </dl>
              <p className="mt-4 text-xs font-medium text-ink-muted">Consumers</p>
              <ul className="mt-1 divide-y divide-hairline/60">
                {(stream?.consumers || []).map((c) => (
                  <li key={c.name} className="flex justify-between py-1.5 text-xs">
                    <span className="font-mono text-ink-secondary truncate">{c.name}</span>
                    <span className="num text-ink-muted">
                      {c.pending} pending · idle {age(c.idle_ms / 1000)}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card title="Leader history" subtitle="Each change of leadership gets a new term">
              {(data.leader?.history || []).length === 0 ? (
                <EmptyState title="No election yet" />
              ) : (
                <ol className="space-y-1.5">
                  {data.leader.history.map((h) => (
                    <li key={h.term} className="flex justify-between text-xs">
                      <span className="text-ink-secondary">
                        term <span className="num text-ink">{h.term}</span> ·{' '}
                        <span className="font-mono">{h.leader}</span>
                      </span>
                      <span className="text-ink-muted">{new Date(h.at * 1000).toLocaleTimeString()}</span>
                    </li>
                  ))}
                </ol>
              )}
            </Card>

            <Card title="Mutual exclusion" subtitle="Per-employee Redis lock around cap check → LLM call → spend">
              <dl className="grid grid-cols-2 gap-y-2 text-sm">
                <dt className="text-ink-muted">Acquired</dt>
                <dd className="num text-right text-ink">{locks.acquired || 0}</dd>
                <dt className="text-ink-muted">Had to wait (contended)</dt>
                <dd className="num text-right text-ink">{locks.contended || 0}</dd>
                <dt className="text-ink-muted">Timed out → 429</dt>
                <dd className="num text-right text-ink">{locks.timeouts || 0}</dd>
              </dl>
              <p className="mt-4 text-xs text-ink-muted">
                Contention appears when several pods serve the same employee at once — try the Employee Simulator
                with one employee and high concurrency.
              </p>
            </Card>
          </div>

          <Card
            className="mt-4"
            title="Recent usage events — Lamport order"
            subtitle="Sorted by (Lamport timestamp, origin pod): one consistent order across all gateway pods"
            bodyClass="pb-2"
          >
            {data.recent_events.length === 0 ? (
              <EmptyState title="No events yet" hint="Send traffic from the Employee Simulator." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-ink-muted">
                      <th className="px-5 py-2 font-medium">Lamport</th>
                      <th className="py-2 font-medium">Employee</th>
                      <th className="py-2 font-medium">Model</th>
                      <th className="py-2 font-medium text-right">Cost</th>
                      <th className="py-2 font-medium">Gateway pod</th>
                      <th className="py-2 pr-5 font-medium">Persisted by</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline/60">
                    {data.recent_events.map((e) => (
                      <tr key={e.event_id}>
                        <td className="px-5 py-1.5 num text-ink">{e.lamport_ts}</td>
                        <td className="py-1.5 text-ink-secondary">{e.user}</td>
                        <td className="py-1.5 text-ink-secondary">{e.model}</td>
                        <td className="py-1.5 num text-right text-ink-secondary">
                          {currency(e.cost_usd, { decimals: 5 })}
                        </td>
                        <td className="py-1.5 font-mono text-ink-muted">{e.origin_pod}</td>
                        <td className="py-1.5 pr-5 font-mono text-ink-muted">{e.processed_by}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </>
  )
}
