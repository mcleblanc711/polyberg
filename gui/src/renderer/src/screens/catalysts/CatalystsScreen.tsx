import { useState, type CSSProperties } from 'react'
import { CatalystForm } from '../../components/CatalystForm'
import { usePmData } from '../../lib/pmDataContext'
import { colors as C, fonts as F } from '../../styles/tokens'
import type { Market } from '../../lib/types'

export const CatalystsScreen = () => {
  const pmData = usePmData()
  const activeMarkets = pmData.markets.filter((m) => !m.expired)
  const expiredMarkets = pmData.markets.filter((m) => m.expired)
  const [mid, setMid] = useState<string>(activeMarkets[0]?.id ?? pmData.markets[0]?.id ?? '')
  const [adding, setAdding] = useState(false)
  const [showExpired, setShowExpired] = useState(false)
  const m = pmData.marketById(mid) ?? activeMarkets[0] ?? pmData.markets[0]
  if (!m) {
    return (
      <div style={S.root}>
        <div style={S.h1Sub}>// no markets in registry — add one on the MARKETS tab</div>
      </div>
    )
  }

  const marketRow = (mm: Market, dimmed: boolean): JSX.Element => {
    const on = mm.id === mid
    return (
      <div
        key={mm.id}
        onClick={() => setMid(mm.id)}
        style={{
          padding: '10px 10px',
          cursor: 'pointer',
          borderLeft: '2px solid',
          borderLeftColor: on ? C.magenta : 'transparent',
          background: on ? C.magentaDim : 'transparent',
          marginBottom: 4,
          opacity: dimmed && !on ? 0.55 : 1
        }}
      >
        <div
          style={{
            fontSize: 11.5,
            fontFamily: F.display,
            fontWeight: on ? 700 : 500,
            color: on ? C.magenta : C.cyanText
          }}
        >
          {mm.id}
        </div>
        <div
          style={{
            fontSize: 10,
            color: mm.catalysts.length > 0 ? C.textDim : C.textMute,
            fontFamily: F.mono,
            marginTop: 2
          }}
        >
          {mm.catalysts.length} entries
        </div>
      </div>
    )
  }

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.h1}>CATALYST EDITOR</div>
          <div style={S.h1Sub}>
            // recent_catalysts.md · per-market timeline · append here or via INTAKE — edit the file
            directly to amend old entries
          </div>
        </div>
        <button style={S.btnGhost} onClick={() => setAdding((a) => !a)}>
          {adding ? '✕ CANCEL' : '+ NEW CATALYST'}
        </button>
      </div>
      {adding && m ? (
        <CatalystForm marketId={m.id} onCancel={() => setAdding(false)} />
      ) : null}
      <div style={S.grid}>
        <div style={S.panel}>
          <div style={S.panelHdr}>// markets · {activeMarkets.length} active</div>
          {activeMarkets.map((mm) => marketRow(mm, false))}
          {expiredMarkets.length > 0 && (
            <>
              <button style={S.expiredToggle} onClick={() => setShowExpired((v) => !v)}>
                {showExpired ? '▾' : '▸'} {expiredMarkets.length} expired
              </button>
              {showExpired && expiredMarkets.map((mm) => marketRow(mm, true))}
            </>
          )}
        </div>
        <div style={S.panel}>
          <div style={S.panelHdr}>
            // {m.id} · {m.catalysts.length} catalysts
          </div>
          {m.catalysts.length === 0 && !adding && (
            <div style={S.emptyPanel}>
              <div>no catalysts recorded for this market yet</div>
              <button style={{ ...S.btnGhost, marginTop: 12 }} onClick={() => setAdding(true)}>
                + ADD CATALYST
              </button>
              <div style={S.emptyHint}>
                or paste tweets/articles into the INTAKE tab to auto-tag them
              </div>
            </div>
          )}
          {m.catalysts.map((c, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                gap: 12,
                padding: '10px 0',
                borderBottom: `1px solid ${C.line2}`
              }}
            >
              <div style={{ minWidth: 140 }}>
                <div
                  style={{
                    color: C.magenta,
                    fontFamily: F.mono,
                    fontSize: 10.5,
                    letterSpacing: 0.4,
                    textShadow: `0 0 4px ${C.magenta}66`
                  }}
                >
                  {c.t}
                </div>
                <div
                  style={{
                    ...S.chip,
                    color: C.cyan,
                    borderColor: C.cyan,
                    display: 'inline-block',
                    marginTop: 4
                  }}
                >
                  {c.src}
                </div>
              </div>
              <div
                style={{
                  flex: 1,
                  fontSize: 12.5,
                  color: C.cyanText,
                  lineHeight: 1.5,
                  fontFamily: F.body
                }}
              >
                {c.txt}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

const S: Record<string, CSSProperties> = {
  root: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
    padding: 18,
    gap: 14,
    overflow: 'auto'
  },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between'
  },
  h1: {
    fontSize: 18,
    fontWeight: 700,
    fontFamily: F.display,
    letterSpacing: 1,
    color: C.text
  },
  h1Sub: {
    fontSize: 11,
    color: C.textDim,
    fontFamily: F.mono,
    marginTop: 3,
    letterSpacing: 0.4
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: '260px 1fr',
    gap: 12,
    flex: 1,
    minHeight: 0
  },
  panel: {
    background: C.bgPanel,
    border: `1px solid ${C.line}`,
    padding: 14,
    overflow: 'auto'
  },
  panelHdr: {
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 0.8,
    fontWeight: 700,
    fontFamily: F.mono,
    marginBottom: 10,
    textShadow: `0 0 4px ${C.magenta}66`,
    display: 'flex',
    alignItems: 'center',
    gap: 14
  },
  expiredToggle: {
    background: 'transparent',
    border: 'none',
    color: C.textMute,
    fontFamily: F.mono,
    fontSize: 10,
    letterSpacing: 0.8,
    cursor: 'pointer',
    padding: '10px 10px 6px',
    outline: 'none',
    display: 'block'
  },
  emptyPanel: {
    border: `1px dashed ${C.line}`,
    background: C.bgRow,
    padding: 28,
    textAlign: 'center',
    color: C.textDim,
    fontFamily: F.body,
    fontSize: 12.5
  },
  emptyHint: {
    marginTop: 12,
    fontSize: 10.5,
    color: C.textMute,
    fontFamily: F.mono,
    letterSpacing: 0.3
  },
  chip: {
    padding: '2px 7px',
    border: '1px solid',
    fontSize: 9.5,
    fontFamily: F.mono,
    fontWeight: 700,
    letterSpacing: 0.4,
    textTransform: 'uppercase'
  },
  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '4px 10px',
    fontFamily: F.mono,
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none'
  }
}
