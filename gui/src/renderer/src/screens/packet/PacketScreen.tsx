import type { CSSProperties } from 'react'
import { colors as C, fonts as F } from '../../styles/tokens'

const PACKET_YAML = `packet:
  generated:    2026-05-08T13:00:00Z
  freshness:    PASS  (all imports < 60min)
  markets:      3
  positions:    3
  open_orders:  4
  thesis:       "Hormuz status-quo bias persists…"
  constraints:
    - single_market_max_pct: 30
    - min_days_to_resolution: 7
  attachments:
    - portfolio_current.yaml
    - open_orders.yaml
    - recent_catalysts.md
    - snapshots/2026-05-08T13-24Z.json`

const ADJUDICATOR_STATUS = `status:        AWAITING
last_validate: 13:21Z  (pass)
last_input:    adjudicator_input.yaml  (47KB)
next_action:   $ validate-adjudicator
              → build-trade-ticket`

export const PacketScreen = () => {
  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.h1}>PACKET REVIEW</div>
          <div style={S.h1Sub}>// build-packet output → adjudicator input → trade ticket</div>
        </div>
      </div>
      <div style={S.grid}>
        <div style={S.panel}>
          <div style={S.panelHdr}>// packet.yaml · last build 13:00Z</div>
          <pre style={S.code}>{PACKET_YAML}</pre>
        </div>
        <div style={S.panel}>
          <div style={S.panelHdr}>// adjudicator response · pending</div>
          <pre style={{ ...S.code, color: C.amber }}>{ADJUDICATOR_STATUS}</pre>
          <div style={{ ...S.panelHdr, marginTop: 14 }}>// proposed actions · 0 ready</div>
          <div style={S.waiting}>
            waiting for adjudicator validation · run next stage to proceed
          </div>
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
  },
  waiting: {
    padding: 16,
    color: C.textMute,
    fontFamily: F.mono,
    fontSize: 11.5,
    textAlign: 'center',
    border: `1px dashed ${C.line}`
  }
}
