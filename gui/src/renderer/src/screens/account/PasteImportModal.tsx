import { useEffect, useState, type CSSProperties } from 'react'
import type { PasteKind } from '../../../../shared/contract'
import { usePmDataRefresh } from '../../lib/pmDataContext'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'

type PasteState =
  | { kind: 'idle' }
  | { kind: 'previewing' }
  | { kind: 'preview'; yaml: string }
  | { kind: 'writing' }
  | { kind: 'ok' }
  | { kind: 'error'; message: string }

const SCHEMA_HINT: Record<PasteKind, string> = {
  portfolio: `{
  "as_of": "2026-05-11T00:00:00+00:00",   // optional; auto-filled if omitted
  "portfolio_value": 200.0,
  "cash_available": 50.0,
  "positions": [
    {
      "market_id": "<must match market_registry.yaml>",
      "market_name": "...",
      "side": "YES" | "NO",
      "avg_price": 0.0..1.0,
      "mark_price": 0.0..1.0,
      "shares": >= 0,
      "current_value": >= 0,
      "pnl": <signed>,
      "thesis_bucket": ""
    }
  ]
}`,
  orders: `{
  "as_of": "2026-05-11T00:00:00+00:00",   // optional; auto-filled if omitted
  "buy_orders": [
    {
      "market_id": "<must match market_registry.yaml>",
      "side": "YES" | "NO",
      "price": 0.0..1.0,
      "shares": >= 0,
      "order_type": "limit",
      "notes": ""
    }
  ],
  "sell_orders": []
}`
}

const CANONICAL_TARGET: Record<PasteKind, string> = {
  portfolio: 'context/portfolio_current.yaml',
  orders: 'context/open_orders.yaml'
}

export const PasteImportModal = ({ onClose }: { onClose: () => void }) => {
  const refresh = usePmDataRefresh()
  const [kind, setKind] = useState<PasteKind>('orders')
  const [text, setText] = useState('')
  const [state, setState] = useState<PasteState>({ kind: 'idle' })

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const startPreview = async (): Promise<void> => {
    setState({ kind: 'previewing' })
    try {
      const inputPath = await window.pm.writePasteInput(kind, text)
      const result = await window.pm.runStage('paste-import', [
        '--kind',
        kind,
        '--input',
        inputPath,
        '--dry-run'
      ])
      if (!result.ok) {
        setState({
          kind: 'error',
          message: result.stderr || result.stdout || `exit ${result.code}`
        })
        return
      }
      setState({ kind: 'preview', yaml: result.stdout })
    } catch (err) {
      setState({ kind: 'error', message: String(err) })
    }
  }

  const commit = async (): Promise<void> => {
    setState({ kind: 'writing' })
    try {
      const inputPath = await window.pm.writePasteInput(kind, text)
      const result = await window.pm.runStage('paste-import', [
        '--kind',
        kind,
        '--input',
        inputPath
      ])
      if (!result.ok) {
        setState({
          kind: 'error',
          message: result.stderr || result.stdout || `exit ${result.code}`
        })
        return
      }
      await refresh()
      setState({ kind: 'ok' })
    } catch (err) {
      setState({ kind: 'error', message: String(err) })
    }
  }

  return (
    <div style={S.backdrop} onClick={onClose}>
      <div style={S.card} onClick={(e) => e.stopPropagation()}>
        <div style={S.hdr}>// paste-import → manual canonical-JSON path</div>
        <div style={S.sub}>
          For users without CLOB credentials. Paste JSON matching the canonical Pydantic schema;
          polyberg validates it and writes{' '}
          <span style={{ color: C.cyan, fontFamily: F.mono }}>{CANONICAL_TARGET[kind]}</span>.
          No automation, no execution. Typical flow: drop the schema block on the right into Claude
          / ChatGPT alongside a Polymarket UI screenshot, ask it to return strict JSON matching this
          shape, then paste here.
        </div>

        <div style={S.tabRow}>
          {(['orders', 'portfolio'] as PasteKind[]).map((k) => {
            const on = kind === k
            return (
              <button
                key={k}
                style={{ ...S.tab, ...(on ? S.tabActive : null) }}
                onClick={() => {
                  setKind(k)
                  setState({ kind: 'idle' })
                }}
              >
                {k === 'orders' ? 'OPEN ORDERS JSON' : 'PORTFOLIO JSON'}
              </button>
            )
          })}
        </div>

        <div style={S.body}>
          <div style={S.col}>
            <div style={S.colHdr}>// paste here</div>
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value)
                if (state.kind !== 'idle') setState({ kind: 'idle' })
              }}
              spellCheck={false}
              placeholder={'{\n  ...\n}'}
              style={S.textarea}
            />
          </div>
          <div style={S.col}>
            <div style={S.colHdr}>// canonical schema</div>
            <pre style={S.schemaBox}>{SCHEMA_HINT[kind]}</pre>
            {state.kind === 'preview' && (
              <>
                <div style={{ ...S.colHdr, marginTop: 12 }}>// preview · validated YAML</div>
                <pre style={S.previewBox}>{state.yaml}</pre>
              </>
            )}
            {state.kind === 'error' && (
              <pre style={S.errorBox}>{state.message.slice(0, 1500)}</pre>
            )}
          </div>
        </div>

        <div style={S.btnRow}>
          <div style={S.statusLine}>
            {state.kind === 'idle' && (
              <span style={{ color: C.textMute }}>
                paste, then VALIDATE — nothing is written until CONFIRM
              </span>
            )}
            {state.kind === 'previewing' && (
              <span style={{ color: C.amber }}>validating…</span>
            )}
            {state.kind === 'writing' && <span style={{ color: C.amber }}>writing…</span>}
            {state.kind === 'ok' && (
              <span style={{ color: C.cyan }}>● wrote {CANONICAL_TARGET[kind]}</span>
            )}
          </div>
          <button style={S.btnGhost} onClick={onClose}>
            CLOSE
          </button>
          <button
            style={S.btnSecondary}
            onClick={startPreview}
            disabled={!text.trim() || state.kind === 'previewing' || state.kind === 'writing'}
          >
            VALIDATE &amp; PREVIEW
          </button>
          <button
            style={S.btnPrimary}
            onClick={commit}
            disabled={state.kind !== 'preview'}
            title={
              state.kind !== 'preview' ? 'Run VALIDATE & PREVIEW first to enable CONFIRM' : ''
            }
          >
            CONFIRM · WRITE FILE ▸
          </button>
        </div>
      </div>
    </div>
  )
}

const S: Record<string, CSSProperties> = {
  backdrop: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.7)',
    backdropFilter: 'blur(2px)',
    zIndex: 200,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center'
  },
  card: {
    width: 'min(1100px, 96vw)',
    maxHeight: '94vh',
    overflowY: 'auto',
    background: C.bgPanel,
    border: `1px solid ${C.magenta}`,
    boxShadow: `0 0 32px ${C.magenta}55`,
    padding: 18,
    clipPath: clipCard,
    display: 'flex',
    flexDirection: 'column',
    gap: 12
  },
  hdr: {
    fontSize: 12,
    color: C.magenta,
    fontFamily: F.mono,
    letterSpacing: 0.7,
    fontWeight: 600,
    textShadow: `0 0 4px ${C.magenta}66`
  },
  sub: { fontSize: 11.5, color: C.textDim, lineHeight: 1.55, maxWidth: 880 },
  tabRow: { display: 'flex', gap: 0, borderBottom: `1px solid ${C.line}` },
  tab: {
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    color: C.textDim,
    padding: '8px 14px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 0.7,
    cursor: 'pointer',
    outline: 'none'
  },
  tabActive: {
    color: C.cyan,
    borderBottom: `2px solid ${C.cyan}`,
    textShadow: `0 0 6px ${C.cyan}66`
  },
  body: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 },
  col: { display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 },
  colHdr: {
    fontSize: 10.5,
    color: C.textMute,
    fontFamily: F.mono,
    letterSpacing: 0.5
  },
  textarea: {
    minHeight: 320,
    background: C.bg,
    color: C.text,
    border: `1px solid ${C.line2}`,
    padding: 12,
    fontFamily: F.mono,
    fontSize: 12,
    lineHeight: 1.5,
    resize: 'vertical',
    outline: 'none'
  },
  schemaBox: {
    background: C.bg,
    border: `1px solid ${C.line2}`,
    padding: 12,
    fontSize: 11,
    fontFamily: F.mono,
    lineHeight: 1.5,
    color: C.textDim,
    margin: 0,
    whiteSpace: 'pre-wrap',
    maxHeight: 240,
    overflowY: 'auto'
  },
  previewBox: {
    background: C.bg,
    border: `1px solid ${C.cyan}66`,
    padding: 12,
    fontSize: 11,
    fontFamily: F.mono,
    lineHeight: 1.5,
    color: C.cyan,
    margin: 0,
    whiteSpace: 'pre-wrap',
    maxHeight: 240,
    overflowY: 'auto'
  },
  errorBox: {
    background: C.bg,
    border: `1px solid ${C.red}`,
    padding: 12,
    fontSize: 11,
    fontFamily: F.mono,
    lineHeight: 1.5,
    color: C.red,
    margin: 0,
    whiteSpace: 'pre-wrap',
    maxHeight: 240,
    overflowY: 'auto'
  },
  btnRow: { display: 'flex', alignItems: 'center', gap: 10 },
  statusLine: { flex: 1, fontFamily: F.mono, fontSize: 11, letterSpacing: 0.4 },
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
  btnSecondary: {
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
