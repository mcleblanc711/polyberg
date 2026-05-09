import type { CSSProperties } from 'react'
import { fmtPct, fmtUsd } from '../../lib/format'
import { pmData } from '../../lib/pmData'
import { colors as C, fonts as F } from '../../styles/tokens'

const BigMetric = ({
  k,
  v,
  sub,
  hint,
  positive
}: {
  k: string
  v: string | number
  sub?: string
  hint?: string
  positive?: boolean
}) => {
  const color = positive == null ? C.text : positive ? C.cyan : C.red
  const glow =
    positive == null
      ? 'none'
      : positive
        ? `0 0 12px rgba(0,255,209,0.35)`
        : `0 0 12px rgba(255,61,107,0.35)`
  return (
    <div style={S.bigMetric}>
      <div style={S.bigMetricK}>{k}</div>
      <div style={{ ...S.bigMetricV, color, textShadow: glow }}>{v}</div>
      {sub ? <div style={{ ...S.bigMetricSub, color }}>{sub}</div> : null}
      {hint ? <div style={S.bigMetricHint}>{hint}</div> : null}
    </div>
  )
}

export const MetricStrip = () => {
  const dayPos = pmData.dayPnl >= 0
  return (
    <div style={S.metricStrip}>
      <BigMetric k="EQUITY" v={fmtUsd(pmData.equity)} hint="cash + open positions" />
      <BigMetric
        k="DAY P/L"
        v={fmtUsd(pmData.dayPnl, true)}
        sub={fmtPct((pmData.dayPnl / pmData.equity) * 100, true)}
        positive={dayPos}
      />
      <BigMetric k="OPEN P/L" v={fmtUsd(pmData.totalPnl, true)} positive={pmData.totalPnl >= 0} hint="vs avg cost" />
      <BigMetric k="CASH" v={fmtUsd(pmData.liveState.cash)} hint="available · USDC" />
      <BigMetric k="POSITIONS" v={pmData.positions.length} hint={`${pmData.openOrders.length} open orders`} />
    </div>
  )
}

export const HeatStrip = () => {
  return (
    <div style={S.heat}>
      {pmData.heat.map((h) => {
        const intensity = Math.min(1, Math.abs(h.d) / 4)
        const accent = h.d >= 0 ? C.cyan : C.red
        const glowRgb = h.d >= 0 ? 'rgba(0,255,209,' : 'rgba(255,61,107,'
        const bg = `${glowRgb}${0.04 + intensity * 0.18})`
        const borderColor = `${glowRgb}${0.2 + intensity * 0.4})`
        return (
          <div key={h.id} style={{ ...S.heatCell, background: bg, borderColor }}>
            <div style={S.heatId}>{h.id.replace(/_/g, ' ').slice(0, 18)}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ ...S.heatVal, color: accent, textShadow: `0 0 8px ${accent}88` }}>
                {fmtPct(h.d, true)}
              </div>
              <svg width="32" height="12">
                <path
                  d={`M0 ${h.d >= 0 ? 10 : 2} L32 ${h.d >= 0 ? 2 : 10}`}
                  stroke={accent}
                  strokeWidth={1.5}
                />
              </svg>
            </div>
          </div>
        )
      })}
    </div>
  )
}

const S: Record<string, CSSProperties> = {
  metricStrip: {
    display: 'grid',
    gridTemplateColumns: 'repeat(5, 1fr)',
    borderBottom: `1px solid ${C.line}`,
    background: C.bgPanel,
    flexShrink: 0
  },
  bigMetric: { padding: '12px 18px', borderRight: `1px solid ${C.line}` },
  bigMetricK: { fontSize: 10, color: C.textDim, letterSpacing: 1.5, fontWeight: 600, fontFamily: F.mono },
  bigMetricV: { fontSize: 22, fontWeight: 700, fontFamily: F.mono, marginTop: 4, letterSpacing: -0.5 },
  bigMetricSub: { fontSize: 11, fontFamily: F.mono, marginTop: 2, fontWeight: 600 },
  bigMetricHint: { fontSize: 10, color: C.textMute, marginTop: 2, letterSpacing: 0.4 },
  heat: {
    display: 'flex',
    gap: 5,
    padding: '8px 20px',
    borderBottom: `1px solid ${C.line}`,
    background: C.bg,
    flexShrink: 0
  },
  heatCell: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: 3,
    padding: '6px 10px',
    border: `1px solid`
  },
  heatId: {
    fontSize: 9.5,
    color: C.textDim,
    fontFamily: F.mono,
    letterSpacing: 0.5,
    textTransform: 'uppercase'
  },
  heatVal: { fontSize: 12, fontWeight: 700, fontFamily: F.mono, letterSpacing: 0.4 }
}
