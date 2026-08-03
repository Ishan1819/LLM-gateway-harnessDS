import { useMemo, useState } from 'react'

import { Badge, Meter, StatusPill } from './Primitives'
import { compactNumber, currency, percent } from '../lib/format'

const COLUMNS = [
  { key: 'name', label: 'Name', align: 'left' },
  { key: 'team', label: 'Team', align: 'left' },
  { key: 'requests_today', label: 'Requests today', align: 'right' },
  { key: 'tokens', label: 'Tokens (MTD)', align: 'right' },
  { key: 'spend', label: 'Spend (MTD)', align: 'right' },
  { key: 'pace_pct_of_cap', label: 'Pace against cap', align: 'left' },
]

export default function UserTable({
  users = [],
  selectable = false,
  selected = [],
  onSelect,
  onRowClick,
}) {
  const [sort, setSort] = useState({ key: 'spend', dir: 'desc' })

  const rows = useMemo(() => {
    const copy = [...users]
    copy.sort((a, b) => {
      const x = a[sort.key]
      const y = b[sort.key]
      const cmp = typeof x === 'string' ? x.localeCompare(y) : (x ?? 0) - (y ?? 0)
      return sort.dir === 'asc' ? cmp : -cmp
    })
    return copy
  }, [users, sort])

  function toggleSort(key) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }))
  }

  const allSelected = selectable && users.length > 0 && selected.length === users.length

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-hairline">
            {selectable && (
              <th className="th w-10">
                <input
                  type="checkbox"
                  aria-label="Select all users"
                  className="accent-s1"
                  checked={allSelected}
                  onChange={(e) => onSelect(e.target.checked ? users.map((u) => u.id) : [])}
                />
              </th>
            )}
            {COLUMNS.map((col) => (
              <th key={col.key} className={`th ${col.align === 'right' ? 'text-right' : ''}`}>
                <button
                  className="inline-flex items-center gap-1 hover:text-ink-secondary transition-colors"
                  onClick={() => toggleSort(col.key)}
                >
                  {col.label}
                  <span aria-hidden="true" className="text-[9px]">
                    {sort.key === col.key ? (sort.dir === 'asc' ? '▲' : '▼') : ''}
                  </span>
                </button>
              </th>
            ))}
            <th className="th">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline/60">
          {rows.map((user) => (
            <tr
              key={user.id}
              className={`transition-colors ${
                onRowClick ? 'hover:bg-white/[0.04] cursor-pointer' : 'hover:bg-white/[0.02]'
              }`}
              onClick={onRowClick ? () => onRowClick(user) : undefined}
            >
              {selectable && (
                <td className="td" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label={`Select ${user.name}`}
                    className="accent-s1"
                    checked={selected.includes(user.id)}
                    onChange={(e) =>
                      onSelect(
                        e.target.checked
                          ? [...selected, user.id]
                          : selected.filter((id) => id !== user.id),
                      )
                    }
                  />
                </td>
              )}
              <td className="td">
                <div className="font-medium text-ink">
                  {user.name}
                  {onRowClick && (
                    <span aria-hidden="true" className="ml-1.5 text-ink-muted text-xs">›</span>
                  )}
                </div>
                <div className="text-xs text-ink-muted">{user.email}</div>
              </td>
              <td className="td">{user.team}</td>
              <td className="td num text-right">{compactNumber(user.requests_today)}</td>
              <td className="td num text-right">{compactNumber(user.tokens)}</td>
              <td className="td num text-right text-ink">{currency(user.spend)}</td>
              <td className="td">
                {user.monthly_cap ? (
                  <div className="flex items-center gap-3">
                    <Meter pct={user.pace_pct_of_cap} className="w-20" />
                    <span className="num text-xs text-ink-secondary w-11">
                      {percent(user.pace_pct_of_cap)}
                    </span>
                  </div>
                ) : (
                  <span className="text-xs text-ink-muted">No cap</span>
                )}
              </td>
              <td className="td">
                {!user.is_active ? (
                  <Badge tone="critical">Disabled</Badge>
                ) : user.monthly_cap ? (
                  <StatusPill pct={user.pace_pct_of_cap} />
                ) : (
                  <Badge>Uncapped</Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
