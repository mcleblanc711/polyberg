import type { CSSProperties } from 'react'
import { fmtUsd } from '../../lib/format'
import { usePmData } from '../../lib/pmDataContext'
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
  const pmData = usePmData()
  const buys = pmData.openOrders.filter((o) => o.kind === 'BUY')
  const committed = buys.reduce((a, o) => a + o.px * o.qty, 0)
  return (
    <div style={S.metricStrip}>
      <BigMetric k="EQUITY" v={fmtUsd(pmData.equity)} hint="cash + open positions" />
      <BigMetric
        k="OPEN P/L"
        v={fmtUsd(pmData.totalPnl, true)}
        positive={pmData.totalPnl >= 0}
        hint="vs avg cost"
      />
      <BigMetric k="CASH" v={fmtUsd(pmData.liveState.cash)} hint="available · USDC" />
      <BigMetric
        k="COMMITTED"
        v={fmtUsd(committed)}
        hint={`${buys.length} open buy${buys.length === 1 ? '' : 's'}`}
      />
      <BigMetric
        k="POSITIONS"
        v={pmData.positions.length}
        hint={`${pmData.openOrders.length} open orders`}
      />
    </div>
  )
}

// Live preferred-side quotes from the latest fetch-books run. Hidden entirely
// when no books have been fetched — no dead chrome.
export const HeatStrip = () => {
  const pmData = usePmData()
  if (pmData.heat.length === 0) return null
  return (
    <div style={S.heat}>
      {pmData.heat.map((h) => {
        const accent = h.side === 'YES' ? C.cyan : C.magenta
        return (
          <div key={h.id} style={{ ...S.heatCell, borderColor: `${C.line}` }}>
            <div style={S.heatId}>{h.id.replace(/_/g, ' ').slice(0, 22)}</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <div style={{ ...S.heatVal, color: accent, textShadow: `0 0 8px ${accent}55` }}>
                {(h.px * 100).toFixed(1)}¢
              </div>
              <div style={S.heatSide}>{h.side}</div>
              <div style={S.heatSpread}>±{(h.spread / 2).toFixed(1)}¢</div>
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
    flexShrink: 0,
    overflowX: 'auto'
  },
  heatCell: {
    flex: 1,
    minWidth: 120,
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
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis'
  },
  heatVal: { fontSize: 12, fontWeight: 700, fontFamily: F.mono, letterSpacing: 0.4 },
  heatSide: { fontSize: 9, color: C.textMute, fontFamily: F.mono, fontWeight: 700 },
  heatSpread: { fontSize: 9, color: C.textMute, fontFamily: F.mono }
}
