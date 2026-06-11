import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'

// Shape of the JSON emitted by `polyberg ladder plan --json` (see render.plan_to_dict).
interface CancelRow {
  idx: number
  order_id: string
  market_id: string
  outcome: string
  action: string
  price: number
  shares: number
  reason: string
  replacement_price: number | null
  url: string | null
  paste: string
}
interface PlaceRow {
  idx: number
  market_id: string
  outcome: string
  action: string
  price: number
  shares: number
  purpose: string | null
  url: string | null
  paste: string
}
interface HoldRow {
  idx: number
  order_id: string
  market_id: string
  outcome: string
  action: string
  price: number
  shares: number
  url: string | null
}
interface LadderPlan {
  preflight: string[]
  warnings: string[]
  summary: { cancel: number; place: number; keep: number; unmanaged: number; unmapped: number }
  cancel: CancelRow[]
  place: PlaceRow[]
  keep: HoldRow[]
  unmanaged: HoldRow[]
  unmapped: number
}

type PlanState =
  | { kind: 'idle' }
  | { kind: 'building' }
  | { kind: 'ok'; plan: LadderPlan }
  | { kind: 'fail'; messages: string[] }
  | { kind: 'error'; message: string }

// Per-action outcome, keyed by a stable row key (order_id for cancels, idx for places).
type RowStatus = 'executed' | 'error'
type Confirm =
  | { type: 'cancel'; row: CancelRow }
  | { type: 'place'; row: PlaceRow }
  | null

const fmtPx = (p: number): string => p.toFixed(4)
const fmtSh = (s: number): string => s.toFixed(1)

const parseHardFails = (stderr: string): string[] =>
  stderr
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.startsWith('[hard fail]'))
    .map((l) => l.replace(/^\[hard fail\]\s*/, ''))

export const LadderScreen = (): JSX.Element => {
  const [state, setState] = useState<PlanState>({ kind: 'idle' })
  const [rows, setRows] = useState<Record<string, RowStatus>>({})
  const [confirm, setConfirm] = useState<Confirm>(null)
  const [busy, setBusy] = useState(false)
  const [preflight, setPreflight] = useState<'idle' | 'running' | 'ok' | 'error'>('idle')
  const [preflightMsg, setPreflightMsg] = useState('')

  const buildPlan = async (): Promise<void> => {
    setState({ kind: 'building' })
    setRows({})
    setPreflight('idle')
    setPreflightMsg('')
    const res = await window.pm.runStage('ladder', ['plan', '--json'])
    if (res.code === 2) {
      const messages = parseHardFails(res.stderr)
      setState({ kind: 'fail', messages: messages.length ? messages : [res.stderr.trim()] })
      return
    }
    if (!res.ok) {
      setState({ kind: 'error', message: res.stderr.trim() || `exit ${res.code}` })
      return
    }
    try {
      const parsed = JSON.parse(res.stdout.trim()) as { ok: boolean; plan: LadderPlan }
      if (!parsed.ok || !parsed.plan) {
        setState({ kind: 'error', message: 'Plan JSON missing or malformed' })
        return
      }
      setState({ kind: 'ok', plan: parsed.plan })
    } catch (e) {
      setState({ kind: 'error', message: `Could not parse plan JSON: ${String(e)}` })
    }
  }

  const runPreflight = async (): Promise<void> => {
    setPreflight('running')
    setPreflightMsg('')
    const res = await window.pm.runStage('ladder', ['preflight'])
    if (res.ok) {
      setPreflight('ok')
      setPreflightMsg(res.stdout.trim().slice(0, 200))
    } else {
      setPreflight('error')
      setPreflightMsg((res.stderr.trim() || `exit ${res.code}`).slice(0, 200))
    }
  }

  const doCancel = async (row: CancelRow): Promise<void> => {
    setBusy(true)
    const res = await window.pm.runStage('ladder', ['cancel', '--order-id', row.order_id])
    setRows((r) => ({ ...r, [row.order_id]: res.ok ? 'executed' : 'error' }))
    setBusy(false)
    setConfirm(null)
    if (res.ok) void buildPlan()
  }

  const doRecordManual = async (row: PlaceRow): Promise<void> => {
    setBusy(true)
    const res = await window.pm.runStage('ladder', [
      'record-manual',
      '--market',
      row.market_id,
      '--outcome',
      row.outcome,
      '--side',
      row.action,
      '--price',
      String(row.price),
      '--shares',
      String(row.shares)
    ])
    setRows((r) => ({ ...r, [`place:${row.idx}`]: res.ok ? 'executed' : 'error' }))
    setBusy(false)
    setConfirm(null)
  }

  const copyPaste = (paste: string): void => {
    void window.pm.writeClipboard(paste)
  }

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.title}>LADDER RECONCILIATION</div>
          <div style={S.sub}>
            declare target orders in live/target_ladders.yaml → diff vs live book → confirm each
            action. Cancels go over the API; placements are manual (paste into Polymarket, then mark
            placed).
          </div>
        </div>
        <button style={S.btnPrimary} onClick={() => void buildPlan()} disabled={state.kind === 'building'}>
          {state.kind === 'building' ? 'BUILDING…' : 'BUILD PLAN ▸'}
        </button>
      </div>

      {state.kind === 'idle' && (
        <div style={S.empty}>
          No plan yet. Click <b>BUILD PLAN</b> to diff your target ladders against the live order
          book.
        </div>
      )}

      {state.kind === 'error' && (
        <div style={S.errorBox}>
          <div style={S.errorHdr}>✕ PLAN FAILED</div>
          <pre style={S.errorBody}>{state.message}</pre>
        </div>
      )}

      {state.kind === 'fail' && (
        <div style={S.errorBox}>
          <div style={S.errorHdr}>✕ VALIDATION HARD-FAIL — no plan emitted</div>
          {state.messages.map((m, i) => (
            <div key={i} style={S.errorLine}>
              {m}
            </div>
          ))}
        </div>
      )}

      {state.kind === 'ok' && (
        <Plan
          plan={state.plan}
          rows={rows}
          busy={busy}
          preflight={preflight}
          preflightMsg={preflightMsg}
          onPreflight={() => void runPreflight()}
          onCancel={(row) => setConfirm({ type: 'cancel', row })}
          onMarkPlaced={(row) => setConfirm({ type: 'place', row })}
          onCopy={copyPaste}
        />
      )}

      {confirm && (
        <ConfirmModal
          confirm={confirm}
          busy={busy}
          onClose={() => setConfirm(null)}
          onConfirm={() =>
            confirm.type === 'cancel' ? void doCancel(confirm.row) : void doRecordManual(confirm.row)
          }
        />
      )}
    </div>
  )
}

const Plan = ({
  plan,
  rows,
  busy,
  preflight,
  preflightMsg,
  onPreflight,
  onCancel,
  onMarkPlaced,
  onCopy
}: {
  plan: LadderPlan
  rows: Record<string, RowStatus>
  busy: boolean
  preflight: 'idle' | 'running' | 'ok' | 'error'
  preflightMsg: string
  onPreflight: () => void
  onCancel: (row: CancelRow) => void
  onMarkPlaced: (row: PlaceRow) => void
  onCopy: (paste: string) => void
}): JSX.Element => {
  const s = plan.summary
  return (
    <>
      {plan.warnings.length > 0 && (
        <div style={S.warnBox}>
          <div style={S.warnHdr}>⚠ WARNINGS</div>
          {plan.warnings.map((w, i) => (
            <div key={i} style={S.warnLine}>
              {w}
            </div>
          ))}
        </div>
      )}

      <div style={S.summary}>
        <span style={S.pill}>{s.cancel} CANCEL</span>
        <span style={S.pill}>{s.place} PLACE</span>
        <span style={S.pill}>{s.keep} KEEP</span>
        <span style={S.pill}>{s.unmanaged} UNMANAGED</span>
        <span style={S.pill}>{s.unmapped} UNMAPPED</span>
      </div>

      {plan.preflight.length > 0 && (
        <div style={S.preflightBox}>
          <div style={{ flex: 1 }}>
            <div style={S.preflightHdr}>PRE-FLIGHT REQUIRED</div>
            {plan.preflight.map((p, i) => (
              <div key={i} style={S.preflightLine}>
                {p}
              </div>
            ))}
            {preflightMsg && (
              <div style={{ ...S.preflightLine, color: preflight === 'error' ? C.red : C.cyan }}>
                {preflight === 'error' ? '✕ ' : '● '}
                {preflightMsg}
              </div>
            )}
          </div>
          <button
            style={S.btnAmber}
            onClick={onPreflight}
            disabled={preflight === 'running'}
          >
            {preflight === 'running'
              ? 'RUNNING…'
              : preflight === 'ok'
                ? 'RUN PRE-FLIGHT ✓'
                : 'RUN PRE-FLIGHT ▸'}
          </button>
        </div>
      )}

      {plan.cancel.length > 0 && (
        <Section title="CANCEL">
          {plan.cancel.map((row) => {
            const status = rows[row.order_id]
            return (
              <div key={row.order_id} style={S.row}>
                <RowMeta
                  action={row.action}
                  market={row.market_id}
                  outcome={row.outcome}
                  price={row.price}
                  shares={row.shares}
                  note={
                    row.reason +
                    (row.replacement_price != null
                      ? ` → replace @ ${fmtPx(row.replacement_price)}`
                      : '')
                  }
                />
                <RowActions>
                  <button style={S.btnGhost} onClick={() => onCopy(row.paste)}>
                    COPY
                  </button>
                  {status === 'executed' ? (
                    <span style={S.tagOk}>● CANCELLED</span>
                  ) : status === 'error' ? (
                    <span style={S.tagErr}>✕ ERROR</span>
                  ) : (
                    <button style={S.btnDanger} disabled={busy} onClick={() => onCancel(row)}>
                      CANCEL ORDER ▸
                    </button>
                  )}
                </RowActions>
              </div>
            )
          })}
        </Section>
      )}

      {plan.place.length > 0 && (
        <Section title="PLACE (manual)">
          {plan.place.map((row) => {
            const key = `place:${row.idx}`
            const status = rows[key]
            return (
              <div key={key} style={S.row}>
                <RowMeta
                  action={row.action}
                  market={row.market_id}
                  outcome={row.outcome}
                  price={row.price}
                  shares={row.shares}
                  note={row.purpose || ''}
                />
                <RowActions>
                  <button style={S.btnGhost} onClick={() => onCopy(row.paste)}>
                    COPY
                  </button>
                  {status === 'executed' ? (
                    <span style={S.tagOk}>● PLACED</span>
                  ) : status === 'error' ? (
                    <span style={S.tagErr}>✕ ERROR</span>
                  ) : (
                    <button style={S.btnPrimarySm} disabled={busy} onClick={() => onMarkPlaced(row)}>
                      MARK PLACED ▸
                    </button>
                  )}
                </RowActions>
              </div>
            )
          })}
        </Section>
      )}

      {plan.keep.length > 0 && (
        <Section title="KEEP (already in book)">
          {plan.keep.map((row) => (
            <div key={`keep:${row.idx}`} style={S.row}>
              <RowMeta
                action={row.action}
                market={row.market_id}
                outcome={row.outcome}
                price={row.price}
                shares={row.shares}
                note=""
              />
            </div>
          ))}
        </Section>
      )}

      {plan.unmanaged.length > 0 && (
        <Section title="UNMANAGED (not in target — untouched)">
          {plan.unmanaged.map((row) => (
            <div key={`un:${row.idx}`} style={S.row}>
              <RowMeta
                action={row.action}
                market={row.market_id}
                outcome={row.outcome}
                price={row.price}
                shares={row.shares}
                note=""
              />
            </div>
          ))}
        </Section>
      )}

      {plan.unmapped > 0 && (
        <div style={S.unmappedNote}>
          {plan.unmapped} order(s) not in the registry — surfaced, never cancelled. Run `import-clob-orders`
          to inspect.
        </div>
      )}

      {s.cancel === 0 && s.place === 0 && s.keep === 0 && s.unmanaged === 0 && (
        <div style={S.empty}>Live book already matches the target ladders. Nothing to do.</div>
      )}
    </>
  )
}

const Section = ({ title, children }: { title: string; children: ReactNode }): JSX.Element => (
  <div style={S.section}>
    <div style={S.sectionHdr}>{title}</div>
    {children}
  </div>
)

const RowMeta = ({
  action,
  market,
  outcome,
  price,
  shares,
  note
}: {
  action: string
  market: string
  outcome: string
  price: number
  shares: number
  note: string
}): JSX.Element => (
  <div style={S.rowMeta}>
    <span style={action === 'BUY' ? S.tagBuy : S.tagSell}>{action}</span>
    <span style={S.rowMarket}>{market}</span>
    <span style={outcome === 'YES' ? S.outYes : S.outNo}>{outcome}</span>
    <span style={S.rowNum}>@ {fmtPx(price)}</span>
    <span style={S.rowNum}>× {fmtSh(shares)}</span>
    {note && <span style={S.rowNote}>{note}</span>}
  </div>
)

const RowActions = ({ children }: { children: ReactNode }): JSX.Element => (
  <div style={S.rowActions}>{children}</div>
)

const ConfirmModal = ({
  confirm,
  busy,
  onClose,
  onConfirm
}: {
  confirm: NonNullable<Confirm>
  busy: boolean
  onClose: () => void
  onConfirm: () => void
}): JSX.Element => {
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const row = confirm.row
  const isCancel = confirm.type === 'cancel'
  return (
    <div style={S.modalBackdrop} onClick={onClose}>
      <div style={S.modalCard} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalHdr}>
          {isCancel ? '// cancel order via API' : '// record manual placement'}
        </div>
        <div style={S.modalSub}>
          {isCancel
            ? 'This sends a DELETE /order to the CLOB. It cannot be undone here.'
            : 'You should have already placed this order by hand in Polymarket. This only logs it as manual_confirmed.'}
        </div>
        <div style={S.modalDetail}>
          <Detail k="action" v={row.action} />
          <Detail k="market" v={row.market_id} />
          <Detail k="outcome" v={row.outcome} />
          <Detail k="price" v={fmtPx(row.price)} />
          <Detail k="shares" v={fmtSh(row.shares)} />
          {isCancel && <Detail k="order_id" v={(row as CancelRow).order_id} />}
        </div>
        <div style={S.modalBtns}>
          <button style={S.btnGhost} onClick={onClose}>
            CANCEL
          </button>
          <button
            style={isCancel ? S.btnDanger : S.btnPrimary}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? 'WORKING…' : isCancel ? 'CONFIRM · CANCEL ORDER ▸' : 'CONFIRM · MARK PLACED ▸'}
          </button>
        </div>
      </div>
    </div>
  )
}

const Detail = ({ k, v }: { k: string; v: string }): JSX.Element => (
  <div style={S.detailRow}>
    <span style={S.detailKey}>{k}</span>
    <span style={S.detailVal}>{v}</span>
  </div>
)

const S: Record<string, CSSProperties> = {
  root: { padding: 20, overflowY: 'auto', height: '100%' },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 20,
    marginBottom: 18
  },
  title: { fontFamily: F.display, fontSize: 18, color: C.text, letterSpacing: 1 },
  sub: { fontFamily: F.body, fontSize: 12, color: C.textDim, marginTop: 6, maxWidth: 720 },
  empty: {
    fontFamily: F.body,
    fontSize: 13,
    color: C.textDim,
    padding: 24,
    border: `1px dashed ${C.line}`,
    background: C.bgPanel,
    clipPath: clipCard
  },
  errorBox: {
    border: `1px solid ${C.red}`,
    background: C.redSft,
    padding: 14,
    clipPath: clipCard,
    marginBottom: 14
  },
  errorHdr: { fontFamily: F.mono, fontSize: 12, color: C.red, marginBottom: 8 },
  errorBody: { fontFamily: F.mono, fontSize: 11, color: C.text, whiteSpace: 'pre-wrap', margin: 0 },
  errorLine: { fontFamily: F.mono, fontSize: 11, color: C.text, marginTop: 4 },
  warnBox: {
    border: `1px solid ${C.amber}`,
    background: C.amberSft,
    padding: 12,
    clipPath: clipCard,
    marginBottom: 14
  },
  warnHdr: { fontFamily: F.mono, fontSize: 11, color: C.amber, marginBottom: 6 },
  warnLine: { fontFamily: F.mono, fontSize: 11, color: C.text, marginTop: 3 },
  summary: { display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' },
  pill: {
    fontFamily: F.mono,
    fontSize: 11,
    color: C.textDim,
    border: `1px solid ${C.line}`,
    padding: '4px 10px',
    background: C.bgPanel
  },
  preflightBox: {
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    border: `1px solid ${C.amber}`,
    background: C.amberSft,
    padding: 12,
    clipPath: clipCard,
    marginBottom: 16
  },
  preflightHdr: { fontFamily: F.mono, fontSize: 11, color: C.amber, marginBottom: 4 },
  preflightLine: { fontFamily: F.mono, fontSize: 11, color: C.textDim, marginTop: 2 },
  section: { marginBottom: 20 },
  sectionHdr: {
    fontFamily: F.mono,
    fontSize: 12,
    color: C.magenta,
    letterSpacing: 1,
    marginBottom: 8,
    paddingBottom: 4,
    borderBottom: `1px solid ${C.line}`
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
    padding: '8px 10px',
    background: C.bgRow,
    borderBottom: `1px solid ${C.line2}`
  },
  rowMeta: { display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', flex: 1 },
  rowMarket: { fontFamily: F.mono, fontSize: 12, color: C.text },
  rowNum: { fontFamily: F.mono, fontSize: 12, color: C.textDim },
  rowNote: { fontFamily: F.mono, fontSize: 11, color: C.textMute },
  rowActions: { display: 'flex', alignItems: 'center', gap: 8 },
  tagBuy: { fontFamily: F.mono, fontSize: 11, color: C.cyan, fontWeight: 700 },
  tagSell: { fontFamily: F.mono, fontSize: 11, color: C.magenta, fontWeight: 700 },
  outYes: { fontFamily: F.mono, fontSize: 11, color: C.yes },
  outNo: { fontFamily: F.mono, fontSize: 11, color: C.no },
  tagOk: { fontFamily: F.mono, fontSize: 11, color: C.cyan },
  tagErr: { fontFamily: F.mono, fontSize: 11, color: C.red },
  unmappedNote: {
    fontFamily: F.mono,
    fontSize: 11,
    color: C.textMute,
    padding: 10,
    border: `1px solid ${C.line}`,
    marginBottom: 16
  },
  btnPrimary: {
    fontFamily: F.mono,
    fontSize: 12,
    color: C.bg,
    background: C.magenta,
    border: 'none',
    padding: '8px 14px',
    cursor: 'pointer',
    clipPath: clipCard
  },
  btnPrimarySm: {
    fontFamily: F.mono,
    fontSize: 11,
    color: C.bg,
    background: C.magenta,
    border: 'none',
    padding: '5px 10px',
    cursor: 'pointer'
  },
  btnAmber: {
    fontFamily: F.mono,
    fontSize: 11,
    color: C.bg,
    background: C.amber,
    border: 'none',
    padding: '6px 12px',
    cursor: 'pointer'
  },
  btnDanger: {
    fontFamily: F.mono,
    fontSize: 11,
    color: C.bg,
    background: C.red,
    border: 'none',
    padding: '5px 10px',
    cursor: 'pointer'
  },
  btnGhost: {
    fontFamily: F.mono,
    fontSize: 11,
    color: C.textDim,
    background: 'transparent',
    border: `1px solid ${C.line}`,
    padding: '5px 10px',
    cursor: 'pointer'
  },
  modalBackdrop: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 100
  },
  modalCard: {
    width: 460,
    maxWidth: '90vw',
    background: C.bgPanel,
    border: `1px solid ${C.lineHot}`,
    padding: 20,
    clipPath: clipCard
  },
  modalHdr: { fontFamily: F.mono, fontSize: 13, color: C.text, marginBottom: 8 },
  modalSub: { fontFamily: F.body, fontSize: 12, color: C.textDim, marginBottom: 14 },
  modalDetail: {
    border: `1px solid ${C.line}`,
    background: C.bgRow,
    padding: 12,
    marginBottom: 16
  },
  detailRow: { display: 'flex', justifyContent: 'space-between', padding: '3px 0' },
  detailKey: { fontFamily: F.mono, fontSize: 11, color: C.textMute },
  detailVal: { fontFamily: F.mono, fontSize: 11, color: C.text },
  modalBtns: { display: 'flex', justifyContent: 'flex-end', gap: 10 }
}
