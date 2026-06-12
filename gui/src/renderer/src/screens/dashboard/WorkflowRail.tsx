import type { CSSProperties } from 'react'
import { usePmData } from '../../lib/pmDataContext'
import { useLocalState } from '../../lib/useLocalState'
import { colors as C, fonts as F } from '../../styles/tokens'

export const WorkflowRail = ({
  onRunNextStage,
  nextLabel,
  nextEnabled
}: {
  onRunNextStage: () => void
  nextLabel: string
  nextEnabled: boolean
}) => {
  const pmData = usePmData()
  const [collapsed, setCollapsed] = useLocalState('polyberg:dashboard.railCollapsed', false)
  const staleCount = pmData.workflow.filter((w) => w.state !== 'ok').length

  if (collapsed) {
    return (
      <div style={S.railCollapsed}>
        <button style={S.collapseBtn} title="expand workflow rail" onClick={() => setCollapsed(false)}>
          »
        </button>
        <div style={S.collapsedLabel}>WORKFLOW</div>
        {staleCount > 0 && <div style={S.collapsedBadge}>{staleCount}</div>}
      </div>
    )
  }

  return (
    <div style={S.wfRail}>
      <div style={S.railHdrRow}>
        <div style={S.railHdr}>// research workflow</div>
        <button style={S.collapseBtn} title="collapse workflow rail" onClick={() => setCollapsed(true)}>
          «
        </button>
      </div>
      <div style={S.wfStages}>
        {pmData.workflow.map((w, i) => {
          const c = w.state === 'ok' ? C.cyan : w.state === 'stale' ? C.amber : C.textMute
          const last = i === pmData.workflow.length - 1
          return (
            <div key={w.id} style={S.wfStage}>
              <div style={S.wfStageGlyph}>
                <div
                  style={{
                    ...S.wfStageDot,
                    borderColor: c,
                    background: w.state === 'ok' ? c : 'transparent',
                    color: w.state === 'ok' ? C.bg : c,
                    boxShadow: w.state === 'ok' ? `0 0 8px ${c}88` : 'none'
                  }}
                >
                  {w.state === 'ok' ? '✓' : w.state === 'stale' ? '!' : i + 1}
                </div>
                {last ? null : (
                  <div style={{ ...S.wfStageLine, background: w.state === 'ok' ? c : C.line }} />
                )}
              </div>
              <div style={{ flex: 1, paddingBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <div style={S.wfStageLabel}>{w.label}</div>
                  <div style={S.wfStageTs}>{w.ts}</div>
                </div>
                <div style={S.wfStageCli}>$ {w.cli}</div>
              </div>
            </div>
          )
        })}
      </div>
      <button
        style={{ ...S.btnPrimary, opacity: nextEnabled ? 1 : 0.45 }}
        onClick={onRunNextStage}
        disabled={!nextEnabled}
      >
        <span>RUN NEXT STAGE ▸</span>
        <span style={S.btnPrimarySub}>{nextLabel}</span>
      </button>

      <div style={{ ...S.railHdr, marginTop: 18 }}>// context freshness</div>
      <div style={S.freshList}>
        {pmData.freshness.map((f) => {
          const c = f.state === 'fresh' ? C.cyan : f.state === 'aging' ? C.amber : C.red
          const age = f.age < 60 ? `${f.age}m` : f.age < 1440 ? `${Math.round(f.age / 60)}h` : `${Math.round(f.age / 1440)}d`
          return (
            <div key={f.file} style={S.freshRow}>
              <div style={{ width: 6, height: 6, background: c, boxShadow: `0 0 6px ${c}` }} />
              <div style={S.freshFile}>{f.file}</div>
              <div style={{ ...S.freshAge, color: c }}>{age}</div>
            </div>
          )
        })}
      </div>

    </div>
  )
}

const S: Record<string, CSSProperties> = {
  wfRail: {
    width: 240,
    borderRight: `1px solid ${C.line}`,
    padding: 14,
    background: C.bg,
    overflow: 'auto',
    flexShrink: 0
  },
  railCollapsed: {
    width: 30,
    borderRight: `1px solid ${C.line}`,
    background: C.bg,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 10,
    padding: '10px 0',
    flexShrink: 0
  },
  collapsedLabel: {
    writingMode: 'vertical-rl',
    fontSize: 9,
    color: C.textMute,
    fontFamily: F.mono,
    letterSpacing: 2
  },
  collapsedBadge: {
    background: C.amber,
    color: C.bg,
    fontSize: 9,
    fontWeight: 700,
    fontFamily: F.mono,
    padding: '1px 5px'
  },
  railHdrRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  railHdr: {
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 1.5,
    fontWeight: 600,
    marginBottom: 10,
    fontFamily: F.mono,
    textShadow: `0 0 6px ${C.magenta}66`
  },
  collapseBtn: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.textDim,
    width: 20,
    height: 20,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: F.mono,
    fontSize: 11,
    cursor: 'pointer',
    outline: 'none',
    padding: 0,
    flexShrink: 0
  },
  wfStages: { paddingLeft: 4 },
  wfStage: { display: 'flex', gap: 10 },
  wfStageGlyph: { display: 'flex', flexDirection: 'column', alignItems: 'center', flex: '0 0 22px' },
  wfStageDot: {
    width: 20,
    height: 20,
    border: '1.5px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 10,
    fontWeight: 700,
    fontFamily: F.mono
  },
  wfStageLine: { width: 1.5, flex: 1, marginTop: 2 },
  wfStageLabel: { fontSize: 11.5, fontWeight: 600, fontFamily: F.display, letterSpacing: 0.2 },
  wfStageTs: { fontSize: 9.5, color: C.textMute, fontFamily: F.mono, marginLeft: 'auto' },
  wfStageCli: { fontSize: 10.5, color: C.cyan, fontFamily: F.mono, marginTop: 2, letterSpacing: 0.3 },

  btnPrimary: {
    background: C.magenta,
    color: C.bg,
    border: 'none',
    padding: '6px 14px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.8,
    cursor: 'pointer',
    textTransform: 'uppercase',
    boxShadow: `0 0 14px ${C.magenta}88, 0 0 0 1px ${C.magenta}`,
    width: '100%',
    marginTop: 4,
    outline: 'none',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: 1
  },
  btnPrimarySub: {
    fontSize: 8.5,
    fontWeight: 600,
    letterSpacing: 0.4,
    opacity: 0.8,
    textTransform: 'none'
  },

  freshList: { background: C.bgPanel, border: `1px solid ${C.line}`, padding: 6 },
  freshRow: { display: 'flex', alignItems: 'center', gap: 8, padding: '4px 4px', fontSize: 10.5 },
  freshFile: { flex: 1, color: C.text, fontFamily: F.mono, fontSize: 10.5 },
  freshAge: { fontFamily: F.mono }
}
