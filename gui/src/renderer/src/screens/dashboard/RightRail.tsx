import { useState, type CSSProperties } from 'react'
import { StageRunnerModal } from '../../components/StageRunnerModal'
import { fmtUsd } from '../../lib/format'
import { usePmData } from '../../lib/pmDataContext'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'
import { Treemap } from './charts'

export const RightRail = () => {
  const pmData = usePmData()
  const [runningStage, setRunningStage] = useState<string | null>(null)
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
          <Treemap
            positions={pmData.positions}
            marketById={pmData.marketById}
            w={240}
            h={108}
          />
        </div>
        <div style={{ padding: '0 12px 12px' }}>
          <ExposureBars />
        </div>
      </div>

      <div style={S.rrCard}>
        <div style={S.rrHdr}>// account · read-only</div>
        <div style={{ padding: '4px 12px 12px' }}>
          <KVRow
            k="proxy wallet"
            v={
              pmData.liveState.proxyWallet
                ? `${pmData.liveState.proxyWallet.slice(0, 6)}…${pmData.liveState.proxyWallet.slice(-4)}`
                : 'not configured'
            }
            mono
          />
          <KVRow k="positions" v={`${pmData.positions.length} imported`} />
          <KVRow k="open orders" v={`${pmData.openOrders.length} imported`} />
          <KVRow k="mode" v="GET only" accent={C.cyan} />
          <button style={S.acctBtn} onClick={() => setRunningStage('import-account-snapshot')}>
            $ import-account-snapshot
          </button>
          <button
            style={{ ...S.acctBtn, marginTop: 6 }}
            onClick={() => setRunningStage('fetch-price-history')}
          >
            $ fetch-price-history
          </button>
        </div>
      </div>

      <div style={S.rrCard}>
        <div style={S.rrHdr}>// cash · open buys</div>
        <CashCommitmentBar />
      </div>
      {runningStage && (
        <StageRunnerModal stage={runningStage} onClose={() => setRunningStage(null)} />
      )}
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

const CashCommitmentBar = () => {
  const pmData = usePmData()
  const cash = pmData.liveState.cash
  const committed = pmData.openOrders
    .filter((o) => o.kind === 'BUY')
    .reduce((a, o) => a + o.px * o.qty, 0)

  if (cash <= 0 && committed <= 0) {
    return (
      <div style={{ padding: '4px 12px 12px', color: C.textMute, fontSize: 11, fontFamily: F.mono }}>
        no cash or open buys imported
      </div>
    )
  }

  const overspent = committed > cash
  const overage = Math.max(0, committed - cash)
  const free = Math.max(0, cash - committed)
  const denom = Math.max(cash, committed, 1)
  const committedPct = (committed / denom) * 100
  const freePct = (free / denom) * 100
  const committedColor = overspent ? C.red : C.amber

  return (
    <div style={{ padding: '4px 12px 12px' }}>
      <div style={S.cashBarTrack}>
        <div
          style={{
            width: committedPct + '%',
            height: '100%',
            background: committedColor,
            boxShadow: `0 0 6px ${committedColor}66`
          }}
        />
        <div
          style={{
            width: freePct + '%',
            height: '100%',
            background: C.cyan,
            boxShadow: `0 0 6px ${C.cyan}66`
          }}
        />
      </div>
      <KVRow k="committed" v={fmtUsd(committed)} accent={committedColor} mono />
      <KVRow k="cash on hand" v={fmtUsd(cash)} accent={C.cyan} mono />
      {overspent && <KVRow k="overage" v={fmtUsd(overage)} accent={C.red} mono />}
    </div>
  )
}

const ExposureBars = () => {
  const pmData = usePmData()
  const total = pmData.positions.reduce((a, p) => a + p.shares * p.mark, 0) || 1
  const byCat: Record<string, number> = {}
  pmData.positions.forEach((p) => {
    const m = pmData.marketById(p.marketId)
    if (!m) return
    byCat[m.category] = (byCat[m.category] || 0) + p.shares * p.mark
  })
  const values = Object.values(byCat)
  const maxPct = values.length ? (Math.max(...values) / total) * 100 : 0
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
    overflowY: 'auto',
    overflowX: 'hidden',
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
  cashBarTrack: {
    display: 'flex',
    alignItems: 'center',
    height: 8,
    background: C.line2,
    marginBottom: 8,
    border: `1px solid ${C.line}`
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
