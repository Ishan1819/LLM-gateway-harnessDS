import { Area, AreaChart, ResponsiveContainer } from 'recharts'

/**
 * Stat tile: label · value · optional delta · optional sparkline.
 * The value uses proportional figures — tabular-nums is for aligned columns.
 */
export default function StatsCard({
  label,
  value,
  helper,
  delta,
  deltaLabel,
  invertDelta = false,
  spark,
  accent = '#3b82f6',
}) {
  const hasDelta = delta !== undefined && delta !== null && Number.isFinite(Number(delta))
  const up = Number(delta) > 0
  // On a cost dashboard "up" is bad unless the caller says otherwise.
  const good = invertDelta ? up : !up
  const deltaColor = Number(delta) === 0 ? '#94a3b8' : good ? '#10b981' : '#ef4444'

  return (
    <div className="card px-5 py-4 flex flex-col justify-between min-h-[126px]">
      <p className="text-xs font-medium text-ink-muted">{label}</p>

      <div className="mt-2">
        <p className="text-[28px] leading-none font-semibold text-ink">{value}</p>
        <div className="mt-2 flex items-center gap-2 min-h-[18px]">
          {hasDelta && (
            <span className="inline-flex items-center gap-1 text-xs font-medium" style={{ color: deltaColor }}>
              <span aria-hidden="true">{Number(delta) === 0 ? '→' : up ? '↑' : '↓'}</span>
              {Math.abs(Number(delta)).toFixed(1)}%
              {deltaLabel && <span className="text-ink-muted font-normal">{deltaLabel}</span>}
            </span>
          )}
          {!hasDelta && helper && <span className="text-xs text-ink-muted">{helper}</span>}
        </div>
      </div>

      {spark?.length > 1 && (
        <div className="h-9 -mx-1 mt-2" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={spark} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`spark-${label.replace(/\W/g, '')}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={accent} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={accent} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="cost"
                stroke={accent}
                strokeWidth={2}
                fill={`url(#spark-${label.replace(/\W/g, '')})`}
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
