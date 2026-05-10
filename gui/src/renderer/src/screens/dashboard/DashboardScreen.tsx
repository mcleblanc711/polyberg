import type { CSSProperties } from 'react'
import { usePmData } from '../../lib/pmDataContext'
import { useLocalState } from '../../lib/useLocalState'
import { colors as C, fonts as F } from '../../styles/tokens'
import { PositionCard } from './PositionCard'
import { RightRail } from './RightRail'
import { HeatStrip, MetricStrip } from './Strips'
import { WorkflowRail } from './WorkflowRail'

export const DashboardScreen = ({ onRunNextStage }: { onRunNextStage: () => void }) => {
  const pmData = usePmData()
  const [expanded, setExpanded] = useLocalState<string | null>(
    'polyberg:dashboard.expanded',
    pmData.positions[0]?.marketId ?? null
  )
  return (
    <>
      <MetricStrip />
      <HeatStrip />
      <div style={S.body}>
        <WorkflowRail onRunNextStage={onRunNextStage} />
        <div style={S.main}>
          <div style={S.sectionHdr}>
            <div>
              <div style={S.sectionTitle}>POSITIONS</div>
              <div style={S.sectionSub}>
                {pmData.positions.length} positions · click any to expand
              </div>
            </div>
            <div style={S.filterRow}>
              <button style={S.filterBtnOn}>ALL</button>
              <button style={S.filterBtn}>YES</button>
              <button style={S.filterBtn}>NO</button>
              <span style={{ width: 12 }} />
              <button style={S.filterBtn}>NOTIONAL ↓</button>
            </div>
          </div>
          {pmData.positions.map((p) => (
            <PositionCard
              key={p.marketId}
              p={p}
              expanded={expanded === p.marketId}
              onToggle={() => setExpanded(expanded === p.marketId ? null : p.marketId)}
            />
          ))}
        </div>
        <RightRail />
      </div>
    </>
  )
}

const S: Record<string, CSSProperties> = {
  body: { flex: 1, display: 'flex', minHeight: 0, overflowX: 'auto' },
  main: {
    flex: 1,
    padding: '14px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    minWidth: 0,
    overflow: 'auto'
  },
  sectionHdr: {
    display: 'flex',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    padding: '0 0 4px'
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 700,
    letterSpacing: 1,
    fontFamily: F.display,
    color: C.text
  },
  sectionSub: { fontSize: 11, color: C.textDim, marginTop: 2, fontFamily: F.mono },
  filterRow: { display: 'flex', gap: 4, alignItems: 'center' },
  filterBtn: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.textDim,
    padding: '4px 10px',
    fontSize: 10.5,
    fontFamily: F.mono,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none'
  },
  filterBtnOn: {
    background: C.magentaSft,
    border: `1px solid ${C.magenta}`,
    color: C.magenta,
    padding: '4px 10px',
    fontSize: 10.5,
    fontFamily: F.mono,
    letterSpacing: 0.6,
    cursor: 'pointer',
    fontWeight: 700,
    textShadow: `0 0 6px ${C.magenta}66`,
    textTransform: 'uppercase',
    outline: 'none'
  }
}
