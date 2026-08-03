import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { CHART, TooltipShell, axisTick } from './ChartKit'
import { compactNumber, currency, shortDate } from '../lib/format'

/**
 * Daily spend over time. One series, so no legend box — the card title names
 * what's plotted. The endpoint carries the only direct label.
 */
export default function UsageChart({ data = [], height = 260 }) {
  if (!data.length) return null

  const last = data[data.length - 1]
  const max = Math.max(...data.map((d) => d.cost), 0.01)

  return (
    <div>
      <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 16, right: 56, bottom: 4, left: 4 }}>
          <defs>
            <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
              {/* Area fill is a ~10% wash, never a saturated block. */}
              <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.22} />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke={CHART.grid} strokeWidth={1} vertical={false} />

          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            tick={axisTick}
            tickLine={false}
            axisLine={{ stroke: CHART.axis }}
            minTickGap={28}
          />
          <YAxis
            tick={axisTick}
            tickLine={false}
            axisLine={false}
            width={56}
            tickFormatter={(v) => currency(v, { compact: true, decimals: 0 })}
            domain={[0, Math.ceil(max * 1.15)]}
          />

          <Tooltip
            cursor={{ stroke: CHART.axis, strokeWidth: 1 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const point = payload[0].payload
              return (
                <TooltipShell
                  title={shortDate(point.date)}
                  rows={[
                    { label: 'Spend', value: currency(point.cost), color: '#3b82f6' },
                    { label: 'Requests', value: compactNumber(point.requests) },
                    { label: 'Tokens', value: compactNumber(point.tokens) },
                  ]}
                />
              )
            }}
          />

          <Area
            type="monotone"
            dataKey="cost"
            stroke="none"
            fill="url(#trendFill)"
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="cost"
            stroke="#3b82f6"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            dot={false}
            // End marker: >=8px with a 2px surface ring so it stays legible.
            activeDot={{ r: 4, fill: '#3b82f6', stroke: CHART.surface, strokeWidth: 2 }}
            isAnimationActive={false}
          />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-1 pr-1 text-right text-[11px] text-ink-muted">
        Latest <span className="num font-medium text-ink-secondary">{currency(last.cost)}</span> on{' '}
        {shortDate(last.date)}
      </p>
    </div>
  )
}
