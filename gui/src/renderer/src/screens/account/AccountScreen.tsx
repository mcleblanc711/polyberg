import { useState, type CSSProperties } from 'react'
import { StageRunnerModal } from '../../components/StageRunnerModal'
import { usePmData } from '../../lib/pmDataContext'
import type { AccountImport, AccountImportFile } from '../../lib/types'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'

type SectionId = keyof AccountImport

const SECTIONS: Array<{ id: SectionId; label: string; subtitle: string }> = [
  {
    id: 'positions',
    label: 'POSITIONS',
    subtitle: 'positions_raw.json  vs  portfolio_current.yaml'
  },
  {
    id: 'balances',
    label: 'BALANCES',
    subtitle: 'balances_raw.json  vs  live_state.yaml'
  },
  {
    id: 'openOrders',
    label: 'OPEN ORDERS',
    subtitle: 'open_orders_raw.json  vs  open_orders.yaml'
  }
]

export const AccountScreen = () => {
  const pmData = usePmData()
  const [active, setActive] = useState<SectionId>('positions')
  const [running, setRunning] = useState(false)
  const file = pmData.accountImport[active]
  const anyImported = SECTIONS.some((s) => pmData.accountImport[s.id].exists)

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.h1}>// account import · read-only review</div>
          <div style={S.sub}>
            Imported account JSON (left) side-by-side with canonical context (right). PROMOTE TO
            CONTEXT is gated until a real Polymarket response sample is captured and the normalizer
            is wired against it. For now, this view is a manual-diff aid only.
          </div>
        </div>
        <button style={S.refreshBtn} onClick={() => setRunning(true)}>
          $ import-account-snapshot
        </button>
      </div>

      <div style={S.tabRow}>
        {SECTIONS.map((s) => {
          const on = active === s.id
          const exists = pmData.accountImport[s.id].exists
          return (
            <button
              key={s.id}
              onClick={() => setActive(s.id)}
              style={{ ...S.tab, ...(on ? S.tabActive : null) }}
            >
              <span>{s.label}</span>
              <span
                style={{
                  ...S.tabDot,
                  background: exists ? C.cyan : C.line,
                  boxShadow: exists ? `0 0 6px ${C.cyan}` : 'none'
                }}
              />
            </button>
          )
        })}
      </div>

      <div style={S.sectionSub}>{SECTIONS.find((s) => s.id === active)!.subtitle}</div>

      {!anyImported ? <EmptyState /> : <DiffPanel file={file} />}

      {running && (
        <StageRunnerModal stage="import-account-snapshot" onClose={() => setRunning(false)} />
      )}
    </div>
  )
}

const EmptyState = () => (
  <div style={S.empty}>
    <div style={S.emptyH}>// no account import found</div>
    <div style={S.emptyTxt}>
      Run <span style={{ color: C.magenta, fontFamily: F.mono }}>$ import-account-snapshot</span>{' '}
      (top right) to write{' '}
      <span style={{ color: C.cyan, fontFamily: F.mono }}>
        reports/generated/account/positions_raw.json
      </span>{' '}
      and siblings. They&apos;ll appear here once the file exists.
    </div>
  </div>
)

const DiffPanel = ({ file }: { file: AccountImportFile }) => (
  <div style={S.diffGrid}>
    <DiffPane
      side="imported"
      title={file.filename}
      body={file.payloadJson}
      missing={!file.exists}
      meta={file.exists ? `as_of ${file.asOf}  ·  source ${file.source || '—'}` : ''}
      language="json"
    />
    <DiffPane
      side="canonical"
      title={file.canonicalFilename}
      body={file.canonicalText}
      missing={file.canonicalText === ''}
      meta={file.canonicalText === '' ? '' : 'context/'}
      language="yaml"
    />
    <PromoteRow file={file} />
  </div>
)

const DiffPane = ({
  side,
  title,
  body,
  missing,
  meta,
  language
}: {
  side: 'imported' | 'canonical'
  title: string
  body: string
  missing: boolean
  meta: string
  language: 'json' | 'yaml'
}) => {
  const sideColor = side === 'imported' ? C.cyan : C.magenta
  return (
    <div style={S.pane}>
      <div style={{ ...S.paneHdr, color: sideColor, textShadow: `0 0 4px ${sideColor}66` }}>
        // {side}  ·  {title}
      </div>
      {meta && <div style={S.paneMeta}>{meta}</div>}
      {missing ? (
        <div style={S.paneMissing}>
          {side === 'imported'
            ? 'no import file at reports/generated/account/'
            : 'no canonical file at context/'}
        </div>
      ) : (
        <pre style={{ ...S.code, color: language === 'json' ? C.cyan : C.text }}>{body}</pre>
      )}
    </div>
  )
}

const PromoteRow = ({ file }: { file: AccountImportFile }) => (
  <div style={S.promoteRow}>
    <button style={S.promoteBtn} disabled title="Normalizer not wired against captured response yet">
      PROMOTE TO CONTEXT ▸
    </button>
    <span style={S.promoteNote}>
      {file.exists
        ? 'gated · raw → canonical normalizer requires a captured real-API sample (v2)'
        : 'gated · no import to promote yet'}
    </span>
  </div>
)

const S: Record<string, CSSProperties> = {
  root: { padding: 18, overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 12 },
  header: { display: 'flex', alignItems: 'flex-start', gap: 16 },
  h1: {
    fontSize: 13,
    color: C.magenta,
    letterSpacing: 0.8,
    fontWeight: 600,
    fontFamily: F.mono,
    textShadow: `0 0 6px ${C.magenta}88`
  },
  sub: { fontSize: 12, color: C.textDim, marginTop: 6, lineHeight: 1.55, maxWidth: 720 },
  refreshBtn: {
    marginLeft: 'auto',
    background: 'transparent',
    border: `1px solid ${C.cyan}`,
    color: C.cyan,
    padding: '8px 14px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.7,
    cursor: 'pointer',
    textTransform: 'uppercase',
    boxShadow: `0 0 10px ${C.cyan}33`,
    outline: 'none'
  },
  tabRow: { display: 'flex', gap: 0, borderBottom: `1px solid ${C.line}`, marginTop: 6 },
  tab: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    color: C.textDim,
    padding: '8px 14px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 600,
    cursor: 'pointer',
    letterSpacing: 0.7,
    outline: 'none'
  },
  tabActive: {
    color: C.magenta,
    borderBottom: `2px solid ${C.magenta}`,
    textShadow: `0 0 6px ${C.magenta}66`
  },
  tabDot: { width: 6, height: 6, borderRadius: 0 },
  sectionSub: {
    fontSize: 10.5,
    color: C.textMute,
    fontFamily: F.mono,
    letterSpacing: 0.5
  },
  empty: {
    border: `1px dashed ${C.line}`,
    padding: 24,
    background: C.bgPanel,
    clipPath: clipCard
  },
  emptyH: {
    fontSize: 11,
    color: C.amber,
    fontFamily: F.mono,
    letterSpacing: 0.7,
    fontWeight: 600,
    textShadow: `0 0 4px ${C.amber}66`,
    marginBottom: 8
  },
  emptyTxt: { fontSize: 12.5, color: C.text, lineHeight: 1.6 },
  diffGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 },
  pane: {
    background: C.bgPanel,
    border: `1px solid ${C.line}`,
    padding: 14,
    clipPath: clipCard,
    minHeight: 220
  },
  paneHdr: {
    fontSize: 10.5,
    letterSpacing: 0.7,
    fontWeight: 600,
    fontFamily: F.mono,
    marginBottom: 4
  },
  paneMeta: {
    fontSize: 10,
    color: C.textMute,
    fontFamily: F.mono,
    letterSpacing: 0.4,
    marginBottom: 10
  },
  paneMissing: {
    fontSize: 11.5,
    color: C.textDim,
    fontFamily: F.mono,
    padding: '20px 0',
    fontStyle: 'italic'
  },
  code: {
    background: C.bg,
    border: `1px solid ${C.line2}`,
    padding: 12,
    fontSize: 11.5,
    fontFamily: F.mono,
    lineHeight: 1.55,
    margin: 0,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-all',
    maxHeight: 520,
    overflowY: 'auto'
  },
  promoteRow: {
    gridColumn: '1 / -1',
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    padding: '10px 14px',
    background: C.bgRow,
    border: `1px solid ${C.line2}`
  },
  promoteBtn: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.textMute,
    padding: '8px 14px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.8,
    cursor: 'not-allowed',
    textTransform: 'uppercase',
    outline: 'none'
  },
  promoteNote: {
    fontSize: 11,
    color: C.amber,
    fontFamily: F.mono,
    letterSpacing: 0.4
  }
}
