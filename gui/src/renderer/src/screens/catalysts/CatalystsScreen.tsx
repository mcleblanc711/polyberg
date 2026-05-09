import { useState, type CSSProperties } from 'react'
import { pmData } from '../../lib/pmData'
import { colors as C, fonts as F } from '../../styles/tokens'

export const CatalystsScreen = () => {
  const [mid, setMid] = useState<string>(pmData.markets[0]!.id)
  const m = pmData.marketById(mid) ?? pmData.markets[0]!
  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.h1}>CATALYST EDITOR</div>
          <div style={S.h1Sub}>
            // recent_catalysts.md · per-market timeline · edit / delete / add
          </div>
        </div>
        <button style={S.btnGhost}>+ NEW CATALYST</button>
      </div>
      <div style={S.grid}>
        <div style={S.panel}>
          <div style={S.panelHdr}>// markets</div>
          {pmData.markets.map((mm) => {
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
                  marginBottom: 4
                }}
              >
                <div
                  style={{
                    fontSize: 11.5,
                    fontFamily: F.display,
                    fontWeight: on ? 700 : 500,
                    color: on ? C.magenta : C.text
                  }}
                >
                  {mm.id}
                </div>
                <div
                  style={{
                    fontSize: 10,
                    color: C.textDim,
                    fontFamily: F.mono,
                    marginTop: 2
                  }}
                >
                  {mm.catalysts.length} entries
                </div>
              </div>
            )
          })}
        </div>
        <div style={S.panel}>
          <div style={S.panelHdr}>
            // {m.id} · {m.catalysts.length} catalysts
          </div>
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
                  color: C.text,
                  lineHeight: 1.5,
                  fontFamily: F.body
                }}
              >
                {c.txt}
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                <button style={S.btnGhost}>EDIT</button>
                <button style={{ ...S.btnGhost, color: C.red }}>DEL</button>
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
