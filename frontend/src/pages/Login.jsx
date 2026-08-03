import { useState } from 'react'

import { useSession } from '../App'
import { ErrorNote } from '../components/Primitives'
import { api } from '../services/api'

export default function Login() {
  const { signIn } = useSession()
  const [mode, setMode] = useState('login')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const [email, setEmail] = useState('admin@techcorp.com')
  const [password, setPassword] = useState('demo123')
  const [orgName, setOrgName] = useState('')
  const [orgSlug, setOrgSlug] = useState('')
  const [adminName, setAdminName] = useState('')

  async function submit(event) {
    event.preventDefault()
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
                    placeholder="TechCorp"
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
                    placeholder="techcorp"
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

            <button className="btn-primary w-full" type="submit" disabled={busy}>
              {busy ? 'Working…' : mode === 'login' ? 'Sign in' : 'Create organization'}
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
              <p className="mt-1 text-xs text-ink-muted num">admin@techcorp.com / demo123</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
