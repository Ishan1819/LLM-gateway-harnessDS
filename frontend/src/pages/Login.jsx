import { useState } from 'react'

import { useSession } from '../App'
import { ErrorNote } from '../components/Primitives'
import { api } from '../services/api'
import { PLAN_META, PLAN_ORDER, formatPrice } from '../lib/plans'

const SELF_SERVE_PLAN = 'free'

const PLAN_SUMMARY = {
  free: '5 developers · per-user caps · 7-day history',
  standard: '50 developers · teams, alerts & savings report · 90-day history',
  premium: 'Unlimited · Cost Optimizer & model right-sizing',
}

export default function Login() {
  const { signIn } = useSession()
  const [mode, setMode] = useState('login')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const [email, setEmail] = useState('admin@test.com')
  const [password, setPassword] = useState('demo123')
  const [orgName, setOrgName] = useState('')
  const [orgSlug, setOrgSlug] = useState('')
  const [adminName, setAdminName] = useState('')
  const [plan, setPlan] = useState(SELF_SERVE_PLAN)

  const paidPlanChosen = mode === 'register' && plan !== SELF_SERVE_PLAN

  async function submit(event) {
    event.preventDefault()
    if (paidPlanChosen) {
      setError(
        `The demo is available on the Free plan only. ${PLAN_META[plan].name} is sales-assisted — ` +
          'start on Free and upgrade from inside the dashboard.',
      )
      return
    }

    setBusy(true)
    setError('')
    try {
      const payload =
        mode === 'login'
          ? await api.login(email, password)
          : await api.register({
              org_name: orgName,
              org_slug: orgSlug,
              admin_name: adminName,
              admin_email: email,
              password,
              monthly_budget: 0,
              plan: SELF_SERVE_PLAN,
            })
      signIn(payload)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-page">
      {/* Value proposition — the half a CTO reads first. */}
      <div className="hidden lg:flex flex-col justify-between p-12 border-r border-hairline/70 bg-card/40">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-s1">
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path
                d="M4 17.5 9.2 11l3.6 3.4L20 6"
                fill="none"
                stroke="white"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="20" cy="6" r="2.2" fill="white" />
            </svg>
          </span>
          <span className="text-base font-semibold tracking-tight">AI Cost Governor</span>
        </div>

        <div className="max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight">
            Know what every LLM call costs — before the invoice arrives.
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-ink-secondary">
            A drop-in proxy between your developers and the model APIs. Your keys stay yours;
            we add per-user attribution, hard budget caps, and the analytics that tell you which
            team is burning the budget.
          </p>

          <ul className="mt-8 space-y-3">
            {[
              'One line changes in your code: the base URL.',
              'Per-user and per-team caps, enforced before the request leaves.',
              'Real-time spend by user, team, and model.',
            ].map((line) => (
              <li key={line} className="flex items-start gap-3 text-sm text-ink-secondary">
                <span aria-hidden="true" className="mt-1 text-[9px] text-good">
                  ●
                </span>
                {line}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-ink-muted">
          Your organization brings its own OpenAI and Anthropic keys. They are encrypted at rest
          and never leave the proxy path.
        </p>
      </div>

      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h1 className="text-2xl font-semibold tracking-tight">
            {mode === 'login' ? 'Sign in' : 'Create your organization'}
          </h1>
          <p className="mt-1.5 text-sm text-ink-muted">
            {mode === 'login'
              ? 'Access your usage dashboard.'
              : 'Set up governance for your team in under a minute.'}
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            {mode === 'register' && (
              <>
                <div>
                  <span className="label">Choose a plan</span>
                  <div className="space-y-2">
                    {PLAN_ORDER.map((id) => {
                      const meta = PLAN_META[id]
                      const selected = plan === id
                      const isFree = id === SELF_SERVE_PLAN
                      return (
                        <label
                          key={id}
                          className={[
                            'flex cursor-pointer items-start gap-3 rounded-lg border px-3.5 py-2.5 transition-colors',
                            selected
                              ? 'border-transparent bg-white/[0.05] ring-1'
                              : 'border-hairline hover:bg-white/[0.03]',
                          ].join(' ')}
                          style={selected ? { '--tw-ring-color': meta.accent } : undefined}
                        >
                          <input
                            type="radio"
                            name="plan"
                            value={id}
                            checked={selected}
                            onChange={() => {
                              setPlan(id)
                              setError('')
                            }}
                            className="mt-1 accent-s1"
                          />
                          <span className="min-w-0 flex-1">
                            <span className="flex items-baseline justify-between gap-2">
                              <span
                                className="text-sm font-medium"
                                style={{ color: selected ? meta.accent : undefined }}
                              >
                                {meta.name}
                              </span>
                              <span className="num shrink-0 text-xs text-ink-muted">
                                {formatPrice(meta.price)}
                              </span>
                            </span>
                            <span className="mt-0.5 block text-[11px] leading-snug text-ink-muted">
                              {PLAN_SUMMARY[id]}
                            </span>
                          </span>
                        </label>
                      )
                    })}
                  </div>

                  {paidPlanChosen && (
                    <p className="mt-2 rounded-lg border border-warning/30 bg-warning/[0.07] px-3 py-2 text-xs text-warning">
                      <span aria-hidden="true" className="mr-1.5">▲</span>
                      The demo is available on the Free plan only. Pick Free to continue —
                      you can upgrade from inside the dashboard.
                    </p>
                  )}
                </div>

                <div>
                  <label className="label" htmlFor="org-name">Organization name</label>
                  <input
                    id="org-name"
                    className="input"
                    value={orgName}
                    onChange={(e) => {
                      setOrgName(e.target.value)
                      setOrgSlug(
                        e.target.value
                          .toLowerCase()
                          .replace(/[^a-z0-9]+/g, '-')
                          .replace(/^-+|-+$/g, ''),
                      )
                    }}
                    placeholder="Acme Inc"
                    required
                  />
                </div>
                <div>
                  <label className="label" htmlFor="org-slug">Proxy slug</label>
                  <input
                    id="org-slug"
                    className="input"
                    value={orgSlug}
                    onChange={(e) => setOrgSlug(e.target.value)}
                    placeholder="acme"
                    pattern="[a-z0-9][a-z0-9-]*"
                    required
                  />
                  <p className="mt-1.5 text-xs text-ink-muted">
                    Your proxy URL will end in <code className="text-ink-secondary">/v1/org/{orgSlug || 'slug'}</code>
                  </p>
                </div>
                <div>
                  <label className="label" htmlFor="admin-name">Your name</label>
                  <input
                    id="admin-name"
                    className="input"
                    value={adminName}
                    onChange={(e) => setAdminName(e.target.value)}
                    required
                  />
                </div>
              </>
            )}

            <div>
              <label className="label" htmlFor="email">Email</label>
              <input
                id="email"
                className="input"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="label" htmlFor="password">Password</label>
              <input
                id="password"
                className="input"
                type="password"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={mode === 'register' ? 8 : undefined}
                required
              />
            </div>

            <ErrorNote message={error} />

            <button
              className="btn-primary w-full"
              type="submit"
              disabled={busy || paidPlanChosen}
            >
              {busy
                ? 'Working…'
                : mode === 'login'
                  ? 'Sign in'
                  : `Create organization on ${PLAN_META[plan].name}`}
            </button>
          </form>

          <button
            className="mt-5 text-xs text-ink-muted hover:text-ink-secondary transition-colors"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login')
              setError('')
            }}
          >
            {mode === 'login'
              ? "Don't have an organization? Create one"
              : 'Already have an account? Sign in'}
          </button>

          {mode === 'login' && (
            <div className="mt-8 rounded-lg border border-hairline bg-card/60 px-4 py-3">
              <p className="text-xs font-medium text-ink-secondary">Demo account</p>
              <p className="mt-1 text-xs text-ink-muted num">admin@test.com / demo123</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
