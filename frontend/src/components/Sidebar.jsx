import { NavLink } from 'react-router-dom'

import { FEATURES, PLAN_META, hasFeature, requiredPlanFor } from '../lib/plans'

const NAV = [
  { to: '/', label: 'Overview', end: true, glyph: '◈' },
  { to: '/teams', label: 'Teams', glyph: '▣', feature: FEATURES.TEAM_CAPS },
  { to: '/users', label: 'Users', glyph: '◍' },
  { to: '/caps', label: 'Cap management', glyph: '⊟' },
  { to: '/alerts', label: 'Alerts', glyph: '△', feature: FEATURES.ALERTS },
  { to: '/savings', label: 'Savings report', glyph: '◑', feature: FEATURES.SAVINGS },
  { to: '/optimizer', label: 'Cost Optimizer', glyph: '◆', feature: FEATURES.OPTIMIZER },
  { to: '/settings', label: 'Settings', glyph: '⚙' },
]

function Logo() {
  return (
    <div className="flex items-center gap-3 px-5 h-16 border-b border-hairline/70">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-s1 shadow-[0_0_18px_-4px_#3b82f6]">
        <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" width="18" height="18" aria-hidden="true">
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
      <div className="leading-tight">
        <p className="text-sm font-semibold tracking-tight text-ink">AI Cost Governor</p>
        <p className="text-[10px] uppercase tracking-widest text-ink-muted">Usage control</p>
      </div>
    </div>
  )
}

export default function Sidebar({ organization, admin, unreadAlerts = 0, onSignOut }) {
  return (
    <aside className="w-60 shrink-0 bg-card border-r border-hairline/70 flex flex-col">
      <Logo />

      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV.map((item) => {
          // Locked items stay visible and clickable — the page itself explains
          // what the feature does, so the lock doubles as the pitch.
          const locked = item.feature && !hasFeature(organization, item.feature)
          const lockAccent = locked ? PLAN_META[requiredPlanFor(item.feature)].accent : null

          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                [
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-s1/12 text-ink font-medium'
                    : 'text-ink-secondary hover:bg-white/[0.04] hover:text-ink',
                ].join(' ')
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    aria-hidden="true"
                    className={`text-xs ${isActive ? 'text-s1' : 'text-ink-muted'}`}
                  >
                    {item.glyph}
                  </span>
                  <span className={locked ? 'text-ink-muted' : undefined}>{item.label}</span>

                  {locked && (
                    <span
                      className="ml-auto text-[9px]"
                      style={{ color: lockAccent }}
                      title={`Available on ${PLAN_META[requiredPlanFor(item.feature)].name}`}
                      aria-label={`Requires ${PLAN_META[requiredPlanFor(item.feature)].name} plan`}
                    >
                      ◆
                    </span>
                  )}

                  {!locked && item.to === '/alerts' && unreadAlerts > 0 && (
                    <span className="ml-auto rounded-full bg-critical/20 px-1.5 py-0.5 text-[10px] font-semibold text-critical num">
                      {unreadAlerts}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          )
        })}
      </nav>

      <div className="border-t border-hairline/70 p-3">
        <div className="rounded-lg bg-page/60 px-3 py-2.5">
          <p className="text-xs font-medium text-ink truncate">{organization?.name}</p>
          <p className="text-[11px] text-ink-muted truncate">{admin?.email}</p>
        </div>
        <button
          onClick={onSignOut}
          className="mt-2 w-full rounded-lg px-3 py-2 text-left text-xs text-ink-muted hover:bg-white/[0.04] hover:text-ink transition-colors"
        >
          Sign out
        </button>
      </div>
    </aside>
  )
}
