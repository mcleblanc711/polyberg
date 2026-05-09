import type { CSSProperties } from 'react'
import { pmData } from '../../lib/pmData'
import { colors as C, fonts as F } from '../../styles/tokens'

export const WorkflowRail = ({ onRunNextStage }: { onRunNextStage: () => void }) => {
  return (
    <div style={S.wfRail}>
      <div style={S.railHdr}>// research workflow</div>
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
      <button style={S.btnPrimary} onClick={onRunNextStage}>
        RUN NEXT STAGE ▸
      </button>

      <div style={{ ...S.railHdr, marginTop: 18 }}>// context freshness</div>
      <div style={S.freshList}>
        {pmData.freshness.map((f) => {
          const c = f.state === 'fresh' ? C.cyan : f.state === 'aging' ? C.amber : C.red
          return (
            <div key={f.file} style={S.freshRow}>
              <div style={{ width: 6, height: 6, background: c, boxShadow: `0 0 6px ${c}` }} />
              <div style={S.freshFile}>{f.file}</div>
              <div style={S.freshAge}>{f.age}m</div>
            </div>
          )
        })}
      </div>

      <div style={{ ...S.railHdr, marginTop: 18 }}>// sentiment · grok</div>
      <div style={S.sentBox}>
        <div style={S.sentRow}>
          <span style={S.sentLabel}>STATUS</span>
          <span style={{ ...S.sentVal, color: C.amber }}>NOT CONNECTED</span>
        </div>
        <div style={S.sentRow}>
          <span style={S.sentLabel}>SOURCE</span>
          <span style={S.sentVal}>{pmData.sentiment.source}</span>
        </div>
        <button style={S.btnGhost}>+ CONNECT GROK</button>
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
  railHdr: {
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 1.5,
    fontWeight: 600,
    marginBottom: 10,
    fontFamily: F.mono,
    textShadow: `0 0 6px ${C.magenta}66`
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

  btnGhost: {
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
    width: 'auto',
    marginTop: 6,
    outline: 'none'
  },
  btnPrimary: {
    background: C.magenta,
    color: C.bg,
    border: 'none',
    padding: '8px 14px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.8,
    cursor: 'pointer',
    textTransform: 'uppercase',
    boxShadow: `0 0 14px ${C.magenta}88, 0 0 0 1px ${C.magenta}`,
    width: '100%',
    marginTop: 4,
    outline: 'none'
  },

  freshList: { background: C.bgPanel, border: `1px solid ${C.line}`, padding: 6 },
  freshRow: { display: 'flex', alignItems: 'center', gap: 8, padding: '4px 4px', fontSize: 10.5 },
  freshFile: { flex: 1, color: C.text, fontFamily: F.mono, fontSize: 10.5 },
  freshAge: { color: C.textDim, fontFamily: F.mono },

  sentBox: { background: C.bgPanel, border: `1px solid ${C.line}`, padding: 8 },
  sentRow: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '3px 0',
    fontSize: 10.5,
    fontFamily: F.mono
  },
  sentLabel: { color: C.textDim, letterSpacing: 0.6 },
  sentVal: { color: C.text, letterSpacing: 0.4 }
}
