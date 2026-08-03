import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { PLAN_META } from '../lib/plans'

/** Plan chip — also the entry point to the upgrade screen. */
export function PlanBadge({ plan, className = '' }) {
  const meta = PLAN_META[plan] || PLAN_META.free
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${className}`}
      style={{ color: meta.accent, backgroundColor: `${meta.accent}1f` }}
    >
      <span aria-hidden="true" className="text-[8px]">◆</span>
      {meta.name}
    </span>
  )
}

export default function TopBar({ organization, admin, onSignOut }) {
  const [open, setOpen] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    function onClickAway(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickAway)
    return () => document.removeEventListener('mousedown', onClickAway)
  }, [])

  const initials = (admin?.name || admin?.email || '?')
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between gap-4 border-b border-hairline/70 bg-page/85 px-8 backdrop-blur">
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-sm font-medium text-ink truncate">{organization?.name}</span>
        <PlanBadge plan={organization?.plan} />
      </div>

      <div className="flex items-center gap-2">
        {organization?.plan !== 'premium' && (
          <Link to="/plan" className="btn-ghost !py-1.5 !px-3 text-xs">
            Upgrade
          </Link>
        )}

        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-white/[0.06]"
            aria-haspopup="menu"
            aria-expanded={open}
          >
            <span className="grid h-7 w-7 place-items-center rounded-full bg-s1/20 text-[11px] font-semibold text-s1">
              {initials}
            </span>
            <span aria-hidden="true" className="text-[9px] text-ink-muted">▼</span>
          </button>

          {open && (
            <div
              role="menu"
              className="absolute right-0 mt-2 w-56 overflow-hidden rounded-lg border border-hairline bg-card shadow-xl"
            >
              <div className="border-b border-hairline/60 px-4 py-3">
                <p className="text-sm font-medium text-ink truncate">{admin?.name}</p>
                <p className="text-xs text-ink-muted truncate">{admin?.email}</p>
              </div>
              <Link
                to="/settings"
                onClick={() => setOpen(false)}
                className="block px-4 py-2.5 text-sm text-ink-secondary transition-colors hover:bg-white/[0.04] hover:text-ink"
                role="menuitem"
              >
                Settings
              </Link>
              <Link
                to="/plan"
                onClick={() => setOpen(false)}
                className="block px-4 py-2.5 text-sm text-ink-secondary transition-colors hover:bg-white/[0.04] hover:text-ink"
                role="menuitem"
              >
                Plan &amp; billing
              </Link>
              <button
                onClick={onSignOut}
                className="w-full border-t border-hairline/60 px-4 py-2.5 text-left text-sm text-critical transition-colors hover:bg-critical/10"
                role="menuitem"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
