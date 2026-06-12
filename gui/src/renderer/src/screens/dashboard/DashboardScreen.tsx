import type { CSSProperties } from 'react'
import { usePmData } from '../../lib/pmDataContext'
import { useLocalState } from '../../lib/useLocalState'
import { colors as C, fonts as F } from '../../styles/tokens'
import { PositionCard } from './PositionCard'
import { RightRail } from './RightRail'
import { HeatStrip, MetricStrip } from './Strips'
import { WorkflowRail } from './WorkflowRail'

type SideFilter = 'ALL' | 'YES' | 'NO'

export const DashboardScreen = ({
  onRunNextStage,
  nextLabel,
  nextEnabled
}: {
  onRunNextStage: () => void
  nextLabel: string
  nextEnabled: boolean
}) => {
  const pmData = usePmData()
  const [expanded, setExpanded] = useLocalState<string | null>(
    'polyberg:dashboard.expanded',
    pmData.positions[0]?.marketId ?? null
  )
  const [sideFilter, setSideFilter] = useLocalState<SideFilter>('polyberg:dashboard.sideFilter', 'ALL')
  const [sortNotional, setSortNotional] = useLocalState('polyberg:dashboard.sortNotional', false)

  const filtered = pmData.positions.filter((p) => sideFilter === 'ALL' || p.side === sideFilter)
  const positions = sortNotional
    ? [...filtered].sort((a, b) => b.shares * b.mark - a.shares * a.mark)
    : filtered

  return (
    <>
      <MetricStrip />
      <HeatStrip />
      <div style={S.body}>
        <WorkflowRail onRunNextStage={onRunNextStage} nextLabel={nextLabel} nextEnabled={nextEnabled} />
        <div style={S.main}>
          <div style={S.sectionHdr}>
            <div>
              <div style={S.sectionTitle}>POSITIONS</div>
              <div style={S.sectionSub}>
                {positions.length}
                {sideFilter !== 'ALL' ? ` of ${pmData.positions.length}` : ''} positions · click any
                to expand
              </div>
            </div>
            <div style={S.filterRow}>
              {(['ALL', 'YES', 'NO'] as const).map((f) => (
                <button
                  key={f}
                  style={sideFilter === f ? S.filterBtnOn : S.filterBtn}
                  onClick={() => setSideFilter(f)}
                >
                  {f}
                </button>
              ))}
              <span style={{ width: 12 }} />
              <button
                style={sortNotional ? S.filterBtnOn : S.filterBtn}
                onClick={() => setSortNotional((v) => !v)}
              >
                NOTIONAL ↓
              </button>
            </div>
          </div>
          {pmData.positions.length === 0 && (
            <div style={S.empty}>
              no positions imported — run <span style={S.emptyCmd}>$ import-account-snapshot</span>{' '}
              from the ACCOUNT tab to pull them from Polymarket
            </div>
          )}
          {pmData.positions.length > 0 && positions.length === 0 && (
            <div style={S.empty}>no {sideFilter} positions — switch the filter back to ALL</div>
          )}
          {positions.map((p) => (
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
  },
  empty: {
    border: `1px dashed ${C.line}`,
    background: C.bgPanel,
    padding: 24,
    color: C.textDim,
    fontFamily: F.body,
    fontSize: 12.5,
    textAlign: 'center'
  },
  emptyCmd: { color: C.magenta, fontFamily: F.mono }
}
