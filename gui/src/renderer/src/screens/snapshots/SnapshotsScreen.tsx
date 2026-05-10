import { useState, type CSSProperties } from 'react'
import { usePmData } from '../../lib/pmDataContext'
import { colors as C, fonts as F } from '../../styles/tokens'
import type { SnapshotMeta } from '../../lib/types'

const renderKv = (s: SnapshotMeta): string =>
  `{
  "ts":            "${s.ts}",
  "markets":       ${s.markets},
  "diffs":         ${s.diffsCount},
  "missing_info":  ${s.missingInfo},
  "generated_by":  "build-snapshot v0.4.1",
  "fresh_minutes": ${s.freshMin}
}`

const DIFF_TEXT = `+ hormuz_normal_may15 · mark 0.76 → 0.78  (+2.0¢)
+ hormuz_normal_may15 · liq +$2,140
= cl_high_120_end_june · no change
- trump_blockade_lifted_apr30 · mark 0.44 → 0.42  (-2.0¢)
+ trump_blockade_lifted_apr30 · spread 3¢ → 4¢   widen`

export const SnapshotsScreen = () => {
  const pmData = usePmData()
  const [active, setActive] = useState<string>(pmData.snapshots[0]?.ts ?? '')
  const cur = pmData.snapshots.find((s) => s.ts === active) ?? pmData.snapshots[0]
  if (!cur) {
    return (
      <div style={S.root}>
        <div style={S.header}>
          <div>
            <div style={S.h1}>SNAPSHOT HISTORY</div>
            <div style={S.h1Sub}>// no snapshots in data/snapshots/ yet</div>
          </div>
        </div>
      </div>
    )
  }
  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.h1}>SNAPSHOT HISTORY</div>
          <div style={S.h1Sub}>// snapshots/ · click row for KV grid + diff vs previous</div>
        </div>
      </div>
      <div style={S.grid}>
        <div style={S.panel}>
          <div style={S.panelHdr}>// timeline · {pmData.snapshots.length} captures</div>
          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>TIMESTAMP</th>
                <th style={S.th}>MARKETS</th>
                <th style={S.th}>DIFFS</th>
                <th style={S.th}>MISSING</th>
              </tr>
            </thead>
            <tbody>
              {pmData.snapshots.map((s) => {
                const on = s.ts === active
                return (
                  <tr
                    key={s.ts}
                    onClick={() => setActive(s.ts)}
                    style={{
                      cursor: 'pointer',
                      background: on ? C.magentaDim : 'transparent'
                    }}
                  >
                    <td
                      style={{
                        ...S.td,
                        color: on ? C.magenta : C.text,
                        fontWeight: on ? 700 : 400
                      }}
                    >
                      {s.ts}
                    </td>
                    <td style={S.td}>{s.markets}</td>
                    <td
                      style={{
                        ...S.td,
                        color: s.diffsCount > 3 ? C.amber : C.cyan
                      }}
                    >
                      {s.diffsCount}
                    </td>
                    <td
                      style={{
                        ...S.td,
                        color: s.missingInfo > 0 ? C.red : C.textMute
                      }}
                    >
                      {s.missingInfo}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div style={S.panel}>
          <div style={S.panelHdr}>// {cur.file}</div>
          <pre style={S.code}>{renderKv(cur)}</pre>
          <div style={{ ...S.panelHdr, marginTop: 14 }}>// diff vs previous capture</div>
          <pre style={S.code}>{DIFF_TEXT}</pre>
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
    gridTemplateColumns: '1fr 1fr',
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
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 11.5,
    fontFamily: F.mono
  },
  th: {
    textAlign: 'left',
    padding: '8px 10px',
    color: C.textDim,
    fontSize: 9.5,
    letterSpacing: 1,
    fontWeight: 700,
    borderBottom: `1px solid ${C.line}`
  },
  td: {
    padding: '8px 10px',
    borderBottom: `1px solid ${C.line2}`,
    color: C.text
  },
  code: {
    background: C.bgRow,
    border: `1px solid ${C.line2}`,
    padding: 12,
    fontFamily: F.mono,
    fontSize: 11.5,
    color: C.cyan,
    lineHeight: 1.65,
    margin: 0,
    whiteSpace: 'pre-wrap'
  }
}
