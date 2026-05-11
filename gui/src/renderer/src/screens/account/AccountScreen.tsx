import { useEffect, useState, type CSSProperties } from 'react'
import { StageRunnerModal } from '../../components/StageRunnerModal'
import { usePmData, usePmDataRefresh } from '../../lib/pmDataContext'
import type { AccountImport, AccountImportFile } from '../../lib/types'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'

type SectionId = keyof AccountImport

const SECTIONS: Array<{ id: SectionId; label: string; subtitle: string; promotable: boolean }> = [
  {
    id: 'positions',
    label: 'POSITIONS',
    subtitle: 'positions_data_api.json  vs  portfolio_current.yaml',
    promotable: true
  },
  {
    id: 'balances',
    label: 'BALANCES',
    subtitle: 'balances_raw.json  vs  live_state.yaml  (PM-US only · not wired)',
    promotable: false
  },
  {
    id: 'openOrders',
    label: 'OPEN ORDERS',
    subtitle: 'open_orders_raw.json  vs  open_orders.yaml  (PM-US only · not wired)',
    promotable: false
  }
]

export const AccountScreen = () => {
  const pmData = usePmData()
  const [active, setActive] = useState<SectionId>('positions')
  const [runningStage, setRunningStage] = useState<string | null>(null)
  const [runningArgs, setRunningArgs] = useState<string[]>([])
  const file = pmData.accountImport[active]
  const anyImported = SECTIONS.some((s) => pmData.accountImport[s.id].exists)
  const wallet = pmData.liveState.proxyWallet
  const section = SECTIONS.find((s) => s.id === active)!

  const runImport = (): void => {
    if (!wallet) {
      alert('No proxy_wallet set in context/live_state.yaml')
      return
    }
    setRunningArgs(['--address', wallet])
    setRunningStage('import-public-positions')
  }

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.h1}>// account import · read-only review</div>
          <div style={S.sub}>
            Imported account JSON (left) side-by-side with canonical context (right). The Positions
            tab uses Polymarket data-api (unauthenticated, wallet-keyed) and supports PROMOTE TO
            CONTEXT. Balances and Open Orders require an authenticated path that's not wired here.
          </div>
          {wallet ? (
            <div style={S.walletLine}>
              proxy_wallet · <span style={{ color: C.cyan }}>{wallet}</span>
            </div>
          ) : (
            <div style={{ ...S.walletLine, color: C.amber }}>
              proxy_wallet missing from live_state.yaml — import will fail
            </div>
          )}
        </div>
        <button style={S.refreshBtn} onClick={runImport} disabled={!wallet}>
          $ import-public-positions
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

      <div style={S.sectionSub}>{section.subtitle}</div>

      {!anyImported ? (
        <EmptyState />
      ) : (
        <DiffPanel file={file} promotable={section.promotable} />
      )}

      {runningStage && (
        <StageRunnerModal
          stage={runningStage}
          args={runningArgs}
          onClose={() => {
            setRunningStage(null)
            setRunningArgs([])
          }}
        />
      )}
    </div>
  )
}

const EmptyState = () => (
  <div style={S.empty}>
    <div style={S.emptyH}>// no account import found</div>
    <div style={S.emptyTxt}>
      Run <span style={{ color: C.magenta, fontFamily: F.mono }}>$ import-public-positions</span>{' '}
      (top right) to write{' '}
      <span style={{ color: C.cyan, fontFamily: F.mono }}>
        reports/generated/account/positions_data_api.json
      </span>
      . It&apos;ll appear here once the file exists.
    </div>
  </div>
)

const DiffPanel = ({ file, promotable }: { file: AccountImportFile; promotable: boolean }) => (
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
    {promotable ? <PromoteRow file={file} /> : <PromoteDisabledRow />}
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

type PromoteState =
  | { kind: 'idle' }
  | { kind: 'previewing' }
  | { kind: 'preview'; yaml: string; skipped: string[] }
  | { kind: 'writing' }
  | { kind: 'ok' }
  | { kind: 'error'; message: string }

const PromoteRow = ({ file }: { file: AccountImportFile }) => {
  const refresh = usePmDataRefresh()
  const [state, setState] = useState<PromoteState>({ kind: 'idle' })

  const startPreview = async (): Promise<void> => {
    setState({ kind: 'previewing' })
    const result = await window.pm.runStage('promote-positions', ['--dry-run'])
    if (!result.ok) {
      setState({ kind: 'error', message: result.stderr || result.stdout || `exit ${result.code}` })
      return
    }
    const skipped = parseSkippedLines(result.stderr)
    setState({ kind: 'preview', yaml: result.stdout, skipped })
  }

  const commit = async (): Promise<void> => {
    setState({ kind: 'writing' })
    const result = await window.pm.runStage('promote-positions', [])
    if (!result.ok) {
      setState({ kind: 'error', message: result.stderr || result.stdout || `exit ${result.code}` })
      return
    }
    await refresh()
    setState({ kind: 'ok' })
  }

  if (!file.exists) {
    return (
      <div style={S.promoteRow}>
        <button style={S.promoteBtn} disabled>
          PROMOTE TO CONTEXT ▸
        </button>
        <span style={S.promoteNote}>gated · no import to promote yet</span>
      </div>
    )
  }

  return (
    <>
      <div style={S.promoteRow}>
        <button
          style={{ ...S.promoteBtn, ...S.promoteBtnArmed }}
          onClick={startPreview}
          disabled={state.kind === 'previewing' || state.kind === 'writing'}
        >
          {state.kind === 'previewing'
            ? 'PREVIEWING…'
            : state.kind === 'writing'
              ? 'WRITING…'
              : 'PROMOTE TO CONTEXT ▸'}
        </button>
        {state.kind === 'ok' && (
          <span style={{ ...S.promoteNote, color: C.cyan }}>
            ● wrote {file.canonicalFilename} · refresh shown
          </span>
        )}
        {state.kind === 'error' && (
          <span style={{ ...S.promoteNote, color: C.red }}>✕ {state.message.slice(0, 200)}</span>
        )}
        {state.kind === 'idle' && (
          <span style={S.promoteNote}>
            preview the normalized YAML before writing · this overwrites {file.canonicalFilename}
          </span>
        )}
      </div>
      {state.kind === 'preview' && (
        <PromotePreviewModal
          yaml={state.yaml}
          skipped={state.skipped}
          canonicalFilename={file.canonicalFilename}
          onCancel={() => setState({ kind: 'idle' })}
          onConfirm={commit}
        />
      )}
    </>
  )
}

const PromoteDisabledRow = () => (
  <div style={S.promoteRow}>
    <button style={S.promoteBtn} disabled>
      PROMOTE TO CONTEXT ▸
    </button>
    <span style={S.promoteNote}>
      gated · only the positions tab has a normalizer wired (data-api). Balances/orders need an
      authenticated path.
    </span>
  </div>
)

const PromotePreviewModal = ({
  yaml,
  skipped,
  canonicalFilename,
  onCancel,
  onConfirm
}: {
  yaml: string
  skipped: string[]
  canonicalFilename: string
  onCancel: () => void
  onConfirm: () => void
}) => {
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  return (
    <div style={S.modalBackdrop} onClick={onCancel}>
      <div style={S.modalCard} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalHdr}>
          // promote preview → <span style={{ color: C.cyan }}>{canonicalFilename}</span>
        </div>
        <div style={S.modalSub}>
          About to overwrite the canonical context file with the YAML below. No file is touched
          until you confirm.
        </div>
        <pre style={S.modalCode}>{yaml}</pre>
        {skipped.length > 0 && (
          <div style={S.skippedBox}>
            <div style={S.skippedHdr}>// skipped {skipped.length} positions</div>
            {skipped.map((s, i) => (
              <div key={i} style={S.skippedLine}>
                {s}
              </div>
            ))}
            <div style={S.skippedHint}>
              Positions are skipped when their conditionId isn&apos;t found in
              market_registry.yaml. Add the condition_id to the registry and re-run.
            </div>
          </div>
        )}
        <div style={S.modalBtns}>
          <button style={S.btnGhost} onClick={onCancel}>
            CANCEL
          </button>
          <button style={S.btnPrimary} onClick={onConfirm}>
            CONFIRM · WRITE FILE ▸
          </button>
        </div>
      </div>
    </div>
  )
}

const parseSkippedLines = (stderr: string): string[] =>
  stderr
    .split('\n')
    .filter((line) => line.trim().startsWith('#'))
    .map((line) => line.replace(/^#\s*/, '').trim())
    .filter((line) => line.length > 0 && !line.startsWith('skipped:'))

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
  walletLine: {
    fontSize: 11,
    color: C.textDim,
    fontFamily: F.mono,
    letterSpacing: 0.4,
    marginTop: 8
  },
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
  promoteBtnArmed: {
    border: `1px solid ${C.magenta}`,
    color: C.magenta,
    cursor: 'pointer',
    boxShadow: `0 0 10px ${C.magenta}33`,
    textShadow: `0 0 4px ${C.magenta}66`
  },
  promoteNote: {
    fontSize: 11,
    color: C.amber,
    fontFamily: F.mono,
    letterSpacing: 0.4
  },
  modalBackdrop: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.7)',
    backdropFilter: 'blur(2px)',
    zIndex: 200,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center'
  },
  modalCard: {
    width: 'min(880px, 90vw)',
    maxHeight: '88vh',
    overflowY: 'auto',
    background: C.bgPanel,
    border: `1px solid ${C.magenta}`,
    boxShadow: `0 0 32px ${C.magenta}55`,
    padding: 20,
    clipPath: clipCard
  },
  modalHdr: {
    fontSize: 12,
    color: C.magenta,
    fontFamily: F.mono,
    letterSpacing: 0.7,
    fontWeight: 600,
    textShadow: `0 0 4px ${C.magenta}66`,
    marginBottom: 6
  },
  modalSub: {
    fontSize: 11.5,
    color: C.textDim,
    lineHeight: 1.55,
    marginBottom: 12
  },
  modalCode: {
    background: C.bg,
    border: `1px solid ${C.line2}`,
    padding: 12,
    fontSize: 11.5,
    fontFamily: F.mono,
    lineHeight: 1.55,
    margin: 0,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-all',
    color: C.text,
    maxHeight: '40vh',
    overflowY: 'auto'
  },
  skippedBox: {
    background: C.bgRow,
    border: `1px solid ${C.amber}`,
    padding: 12,
    marginTop: 12
  },
  skippedHdr: {
    fontSize: 11,
    color: C.amber,
    fontFamily: F.mono,
    letterSpacing: 0.6,
    fontWeight: 600,
    textShadow: `0 0 4px ${C.amber}66`,
    marginBottom: 6
  },
  skippedLine: {
    fontSize: 10.5,
    color: C.textDim,
    fontFamily: F.mono,
    padding: '2px 0',
    wordBreak: 'break-all'
  },
  skippedHint: { fontSize: 10.5, color: C.textMute, marginTop: 8, fontStyle: 'italic' },
  modalBtns: { display: 'flex', gap: 10, marginTop: 14, justifyContent: 'flex-end' },
  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '8px 14px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none'
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
    boxShadow: `0 0 14px ${C.magenta}88`,
    outline: 'none'
  }
}
