import { useState, type CSSProperties } from 'react'
import { StageRunnerModal } from '../../components/StageRunnerModal'
import { usePmData } from '../../lib/pmDataContext'
import { colors as C, fonts as F } from '../../styles/tokens'

const fmtAge = (mins: number): string => {
  if (mins < 60) return `${mins}m`
  if (mins < 1440) return `${Math.round(mins / 60)}h`
  return `${Math.round(mins / 1440)}d`
}

export const SnapshotsScreen = () => {
  const pmData = usePmData()
  const [active, setActive] = useState<string>(pmData.snapshots[0]?.ts ?? '')
  const [runArgs, setRunArgs] = useState<{ stage: string; args?: string[] } | null>(null)
  const cur = pmData.snapshots.find((s) => s.ts === active) ?? pmData.snapshots[0]

  const runner = runArgs && (
    <StageRunnerModal stage={runArgs.stage} args={runArgs.args} onClose={() => setRunArgs(null)} />
  )

  if (!cur) {
    return (
      <div style={S.root}>
        {runner}
        <div style={S.header}>
          <div>
            <div style={S.h1}>SNAPSHOT HISTORY</div>
            <div style={S.h1Sub}>// data/snapshots/ · price + book state captured per run</div>
          </div>
        </div>
        <div style={S.emptyBig}>
          <div>no snapshots in data/snapshots/ yet</div>
          <button
            style={S.btnPrimary}
            onClick={() => setRunArgs({ stage: 'snapshot-markets' })}
          >
            $ snapshot-markets ▸
          </button>
          <div style={S.emptyHint}>
            captures yes/no prices, best bid/ask and depth for every active registry market
          </div>
        </div>
      </div>
    )
  }

  // The snapshot one slot older than the selected capture — the natural
  // --old for diff-snapshots (the list is sorted newest-first).
  const curIdx = pmData.snapshots.findIndex((s) => s.ts === cur.ts)
  const prev = curIdx >= 0 ? pmData.snapshots[curIdx + 1] : undefined

  return (
    <div style={S.root}>
      {runner}
      <div style={S.header}>
        <div>
          <div style={S.h1}>SNAPSHOT HISTORY</div>
          <div style={S.h1Sub}>
            // data/snapshots/ · click a row to inspect · diff runs `diff-snapshots`
          </div>
        </div>
        <button style={S.btnGhost} onClick={() => setRunArgs({ stage: 'snapshot-markets' })}>
          $ SNAPSHOT-MARKETS ▸
        </button>
      </div>
      <div style={S.grid}>
        <div style={S.panel}>
          <div style={S.panelHdr}>// timeline · {pmData.snapshots.length} captures</div>
          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>TIMESTAMP</th>
                <th style={S.th}>MARKETS</th>
                <th style={S.th}>MISSING</th>
                <th style={S.th}>AGE</th>
              </tr>
            </thead>
            <tbody>
              {pmData.snapshots.map((s) => {
                const on = s.ts === cur.ts
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
                        color: s.missingInfo > 0 ? C.amber : C.textMute
                      }}
                    >
                      {s.missingInfo}
                    </td>
                    <td style={{ ...S.td, color: C.textDim }}>{fmtAge(s.freshMin)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div style={S.panel}>
          <div style={S.panelHdr}>
            // {cur.file}
            <span style={{ flex: 1 }} />
            {prev ? (
              <button
                style={S.btnGhost}
                onClick={() =>
                  setRunArgs({
                    stage: 'diff-snapshots',
                    args: ['--old', prev.file, '--new', cur.file]
                  })
                }
              >
                DIFF VS {prev.ts.slice(-10)} ▸
              </button>
            ) : (
              <span style={{ color: C.textMute, fontWeight: 400 }}>oldest capture — no diff base</span>
            )}
          </div>
          <div style={S.metaRow}>
            <Meta k="as_of" v={cur.asOf || '—'} />
            <Meta k="markets" v={String(cur.markets)} />
            <Meta k="missing info" v={String(cur.missingInfo)} warn={cur.missingInfo > 0} />
            <Meta k="captured" v={`${fmtAge(cur.freshMin)} ago`} />
          </div>
          <pre style={S.code}>{cur.preview || '// empty or unreadable snapshot file'}</pre>
        </div>
      </div>
    </div>
  )
}

const Meta = ({ k, v, warn }: { k: string; v: string; warn?: boolean }): JSX.Element => (
  <div style={S.metaCell}>
    <div style={S.metaK}>{k}</div>
    <div style={{ ...S.metaV, color: warn ? C.amber : C.text }}>{v}</div>
  </div>
)

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
  emptyBig: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 14,
    border: `1px dashed ${C.line}`,
    background: C.bgPanel,
    color: C.textDim,
    fontFamily: F.body,
    fontSize: 13
  },
  emptyHint: {
    fontSize: 10.5,
    color: C.textMute,
    fontFamily: F.mono,
    letterSpacing: 0.3
  },
  btnPrimary: {
    background: C.magenta,
    color: C.bg,
    border: 'none',
    padding: '8px 16px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.8,
    cursor: 'pointer',
    textTransform: 'uppercase',
    boxShadow: `0 0 12px ${C.magenta}88`,
    outline: 'none'
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
    overflow: 'auto',
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0
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
    gap: 14,
    flexShrink: 0
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
  metaRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: 6,
    marginBottom: 10,
    flexShrink: 0
  },
  metaCell: { background: C.bgRow, border: `1px solid ${C.line2}`, padding: '6px 10px' },
  metaK: { fontSize: 9.5, color: C.textDim, letterSpacing: 1, fontFamily: F.mono, fontWeight: 600 },
  metaV: { fontSize: 12, fontFamily: F.mono, marginTop: 3, fontWeight: 600 },
  code: {
    background: C.bgRow,
    border: `1px solid ${C.line2}`,
    padding: 12,
    fontFamily: F.mono,
    fontSize: 11,
    color: C.cyan,
    lineHeight: 1.55,
    margin: 0,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    flex: 1,
    minHeight: 0,
    overflow: 'auto'
  }
}
