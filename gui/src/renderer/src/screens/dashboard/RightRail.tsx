import type { CSSProperties } from 'react'
import { fmtUsd } from '../../lib/format'
import { marketById, pmData } from '../../lib/pmData'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'
import { Treemap } from './charts'

export const RightRail = () => {
  return (
    <div style={S.rightRail}>
      <div style={S.rrCard}>
        <div style={S.rrHdr}>// active thesis</div>
        <div style={S.thesisText}>{pmData.liveState.thesis}</div>
        <div style={S.constraintsHdr}>// constraints</div>
        {pmData.liveState.constraints.map((c, i) => (
          <div key={i} style={S.constraint}>
            <span style={{ color: C.magenta, marginRight: 6, textShadow: `0 0 4px ${C.magenta}` }}>
              ›
            </span>
            {c}
          </div>
        ))}
      </div>

      <div style={S.rrCard}>
        <div style={S.rrHdr}>// exposure</div>
        <div style={{ padding: 10 }}>
          <Treemap positions={pmData.positions} w={266} h={108} />
        </div>
        <div style={{ padding: '0 12px 12px' }}>
          <ExposureBars />
        </div>
      </div>

      <div style={S.rrCard}>
        <div style={S.rrHdr}>// account · read-only</div>
        <div style={{ padding: '4px 12px 12px' }}>
          <KVRow k="proxy wallet" v="0xA3…f2D1" mono />
          <KVRow k="positions" v="3 imported · 0 diffs" />
          <KVRow k="open orders" v={`${pmData.openOrders.length} imported`} />
          <KVRow k="last fetch" v="13:42:11 UTC" mono />
          <KVRow k="mode" v="GET only" accent={C.cyan} />
          <button style={S.acctBtn}>$ import-account-snapshot</button>
        </div>
      </div>
    </div>
  )
}

const KVRow = ({
  k,
  v,
  mono,
  accent
}: {
  k: string
  v: string
  mono?: boolean
  accent?: string
}) => (
  <div style={S.kvRow}>
    <span style={S.kvK}>{k}</span>
    <span
      style={{
        ...S.kvV,
        fontFamily: mono ? F.mono : F.body,
        color: accent || C.text
      }}
    >
      {v}
    </span>
  </div>
)

const ExposureBars = () => {
  const total = pmData.positions.reduce((a, p) => a + p.shares * p.mark, 0)
  const byCat: Record<string, number> = {}
  pmData.positions.forEach((p) => {
    const m = marketById(p.marketId)
    if (!m) return
    byCat[m.category] = (byCat[m.category] || 0) + p.shares * p.mark
  })
  const maxPct = (Math.max(...Object.values(byCat)) / total) * 100
  return (
    <>
      {Object.entries(byCat).map(([cat, n]) => {
        const pct = (n / total) * 100
        return (
          <div key={cat} style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', fontSize: 10.5, color: C.textDim, marginBottom: 3 }}>
              <span style={{ flex: 1, letterSpacing: 0.5 }}>{cat.toUpperCase()}</span>
              <span style={{ fontFamily: F.mono, color: C.text }}>
                {fmtUsd(n)} · {pct.toFixed(0)}%
              </span>
            </div>
            <div style={{ height: 5, background: C.line2 }}>
              <div
                style={{
                  width: pct + '%',
                  height: '100%',
                  background: `linear-gradient(90deg, ${C.magenta}, ${C.cyan})`,
                  boxShadow: `0 0 6px ${C.magenta}66`
                }}
              />
            </div>
          </div>
        )
      })}
      <div style={S.cap}>
        <span style={{ color: C.cyan }}>✓</span>
        <span>
          SINGLE-MKT CAP 30% · MAX{' '}
          <span style={{ color: C.text, fontFamily: F.mono }}>{maxPct.toFixed(0)}%</span>
        </span>
      </div>
    </>
  )
}

const S: Record<string, CSSProperties> = {
  rightRail: {
    width: 290,
    borderLeft: `1px solid ${C.line}`,
    padding: 14,
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    background: C.bg,
    overflow: 'auto',
    flexShrink: 0
  },
  rrCard: { background: C.bgPanel, border: `1px solid ${C.line}`, clipPath: clipCard },
  rrHdr: {
    padding: '10px 12px 6px',
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 0.8,
    fontWeight: 600,
    fontFamily: F.mono,
    textShadow: `0 0 4px ${C.magenta}66`
  },
  thesisText: { fontSize: 12, lineHeight: 1.55, padding: '0 12px', color: C.text, fontFamily: F.body },
  constraintsHdr: {
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 0.8,
    fontWeight: 600,
    marginTop: 10,
    padding: '0 12px',
    fontFamily: F.mono,
    textShadow: `0 0 4px ${C.magenta}66`
  },
  constraint: {
    fontSize: 11.5,
    padding: '3px 12px',
    color: C.text,
    lineHeight: 1.4,
    fontFamily: F.body
  },
  cap: {
    fontSize: 10,
    color: C.textDim,
    marginTop: 8,
    paddingTop: 8,
    borderTop: `1px dashed ${C.line}`,
    display: 'flex',
    gap: 6,
    fontFamily: F.mono,
    letterSpacing: 0.5
  },
  kvRow: { display: 'flex', padding: '3px 0', fontSize: 11 },
  kvK: { flex: 1, color: C.textDim, fontFamily: F.mono, letterSpacing: 0.4 },
  kvV: { color: C.text, fontSize: 11 },
  acctBtn: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '7px 12px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 600,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    marginTop: 8,
    width: '100%',
    outline: 'none'
  }
}
