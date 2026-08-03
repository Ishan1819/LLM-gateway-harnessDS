import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { CHART, TooltipShell, axisTick } from './ChartKit'
import { Meter, StatusPill } from './Primitives'
import { compactNumber, currency, percent } from '../lib/format'

/**
 * Spend per team. One measure, so one hue — the category axis carries identity
 * and colour isn't asked to do a job it doesn't have. Cap pressure lives in the
 * table below as an icon + label + meter, never as bar colour.
 */
export function TeamSpendChart({ teams = [], height = 240 }) {
  if (!teams.length) return null
  const data = [...teams].sort((a, b) => a.spend - b.spend)
  const max = Math.max(...data.map((t) => t.spend), 0.01)

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 64, bottom: 4, left: 4 }}
          barCategoryGap="35%"
        >
          <CartesianGrid stroke={CHART.grid} strokeWidth={1} horizontal={false} />
          <XAxis
            type="number"
            tick={axisTick}
            tickLine={false}
            axisLine={{ stroke: CHART.axis }}
            tickFormatter={(v) => currency(v, { compact: true, decimals: 0 })}
            domain={[0, Math.ceil(max * 1.15)]}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ ...axisTick, fill: CHART.inkSecondary }}
            tickLine={false}
            axisLine={false}
            width={104}
          />
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.04)' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const t = payload[0].payload
              return (
                <TooltipShell
                  title={t.name}
                  rows={[
                    { label: 'Spend this month', value: currency(t.spend), color: '#3b82f6' },
                    { label: 'Projected', value: currency(t.projected) },
                    { label: 'Monthly cap', value: currency(t.monthly_cap) },
                    { label: 'Requests', value: compactNumber(t.requests) },
                  ]}
                />
              )
            }}
          />
          <Bar
            dataKey="spend"
            fill="#3b82f6"
            // 4px rounded data-end, square at the baseline.
            radius={[0, 4, 4, 0]}
            maxBarSize={24}
            // Keeps a near-zero team visible instead of collapsing to nothing.
            minPointSize={3}
            isAnimationActive={false}
            label={{
              position: 'right',
              formatter: (v) => currency(v, { decimals: v >= 1000 ? 0 : 2 }),
              fill: CHART.inkSecondary,
              fontSize: 11,
            }}
          >
            {data.map((t) => (
              <Cell key={t.id} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Table view of the same data — the non-colour channel for the chart above. */
export function TeamTable({ teams = [], onEdit }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-hairline">
            <th className="th">Team</th>
            <th className="th">Members</th>
            <th className="th text-right">Spend (MTD)</th>
            <th className="th text-right">Projected</th>
            <th className="th text-right">Monthly cap</th>
            <th className="th w-48">Pace against cap</th>
            {onEdit && <th className="th" />}
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline/60">
          {teams.map((team) => (
            <tr key={team.id} className="hover:bg-white/[0.02] transition-colors">
              <td className="td font-medium text-ink">{team.name}</td>
              <td className="td num">{team.members}</td>
              <td className="td num text-right text-ink">{currency(team.spend)}</td>
              <td className="td num text-right">{currency(team.projected)}</td>
              <td className="td num text-right">
                {team.monthly_cap ? currency(team.monthly_cap, { decimals: 0 }) : '—'}
              </td>
              <td className="td">
                {team.monthly_cap ? (
                  <div className="flex items-center gap-3">
                    <Meter pct={team.pace_pct_of_cap} className="w-20" />
                    <span className="num text-xs text-ink-secondary w-11">
                      {percent(team.pace_pct_of_cap)}
                    </span>
                    <StatusPill pct={team.pace_pct_of_cap} />
                  </div>
                ) : (
                  <span className="text-xs text-ink-muted">No cap set</span>
                )}
              </td>
              {onEdit && (
                <td className="td text-right">
                  <button
                    className="text-xs font-medium text-s1 hover:text-s1/80"
                    onClick={() => onEdit(team)}
                  >
                    Edit caps
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
