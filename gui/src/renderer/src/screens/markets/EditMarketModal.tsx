import { useEffect, useState, type CSSProperties } from 'react'
import { usePmDataRefresh } from '../../lib/pmDataContext'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'

// Shape of the JSON printed by `registry-update --preview`.
interface EditableFields {
  name: string
  category: string
  thesis_bucket: string
  rule_key: string
  oracle_type: string
  preferred_side: 'YES' | 'NO'
  risk_flags: string[]
  notes: string
  market_id: string
  condition_id: string | null
  polymarket_url: string
  resolution_date: string
}

type State =
  | { kind: 'loading' }
  | { kind: 'ready' }
  | { kind: 'saving' }
  | { kind: 'deleting' }
  | { kind: 'confirmDelete' }
  | { kind: 'ok'; verb: string }
  | { kind: 'error'; message: string }

const runErr = (r: { ok: boolean; stderr: string; stdout: string; code: number }): string =>
  r.stderr.trim() || r.stdout.trim() || `exit ${r.code}`

export const EditMarketModal = ({
  marketId,
  onClose
}: {
  marketId: string
  onClose: () => void
}) => {
  const refresh = usePmDataRefresh()
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [locked, setLocked] = useState<{
    conditionId: string | null
    url: string
    resolves: string
  }>({ conditionId: null, url: '', resolves: '' })

  // Editable fields (IDs / resolution_date stay locked — re-add to re-fetch).
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [ruleKey, setRuleKey] = useState('')
  const [oracleType, setOracleType] = useState('')
  const [side, setSide] = useState<'YES' | 'NO'>('NO')
  const [thesisBucket, setThesisBucket] = useState('')
  const [notes, setNotes] = useState('')
  const [riskFlags, setRiskFlags] = useState('')

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    const load = async (): Promise<void> => {
      try {
        const result = await window.pm.runStage('registry-update', [
          '--market-id',
          marketId,
          '--preview'
        ])
        if (cancelled) return
        if (!result.ok) {
          setState({ kind: 'error', message: runErr(result) })
          return
        }
        const f = JSON.parse(result.stdout) as EditableFields
        setName(f.name)
        setCategory(f.category)
        setRuleKey(f.rule_key)
        setOracleType(f.oracle_type)
        setSide(f.preferred_side === 'YES' ? 'YES' : 'NO')
        setThesisBucket(f.thesis_bucket)
        setNotes(f.notes)
        setRiskFlags((f.risk_flags || []).join(', '))
        setLocked({
          conditionId: f.condition_id,
          url: f.polymarket_url,
          resolves: f.resolution_date
        })
        setState({ kind: 'ready' })
      } catch (err) {
        if (!cancelled) setState({ kind: 'error', message: String(err) })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [marketId])

  const save = async (): Promise<void> => {
    setState({ kind: 'saving' })
    try {
      const result = await window.pm.runStage('registry-update', [
        '--market-id',
        marketId,
        '--name',
        name.trim(),
        '--category',
        category.trim(),
        '--rule-key',
        ruleKey.trim(),
        '--oracle-type',
        oracleType.trim(),
        '--preferred-side',
        side,
        '--thesis-bucket',
        thesisBucket.trim(),
        '--notes',
        notes.trim(),
        // Comma string → full replace; empty string clears the list.
        '--risk-flags',
        riskFlags.split(',').map((f) => f.trim()).filter(Boolean).join(', ')
      ])
      if (!result.ok) {
        setState({ kind: 'error', message: runErr(result) })
        return
      }
      await refresh()
      setState({ kind: 'ok', verb: 'updated' })
    } catch (err) {
      setState({ kind: 'error', message: String(err) })
    }
  }

  const remove = async (): Promise<void> => {
    setState({ kind: 'deleting' })
    try {
      const result = await window.pm.runStage('registry-delete', ['--market-id', marketId])
      if (!result.ok) {
        setState({ kind: 'error', message: runErr(result) })
        return
      }
      await refresh()
      setState({ kind: 'ok', verb: 'deleted' })
    } catch (err) {
      setState({ kind: 'error', message: String(err) })
    }
  }

  const saveReady =
    state.kind === 'ready' &&
    !!name.trim() &&
    !!category.trim() &&
    !!ruleKey.trim() &&
    !!oracleType.trim()

  const busy = state.kind === 'saving' || state.kind === 'deleting' || state.kind === 'ok'

  return (
    <div style={S.backdrop} onClick={onClose}>
      <div style={S.card} onClick={(e) => e.stopPropagation()}>
        <div style={S.hdr}>// registry-update → market_registry.yaml</div>
        <div style={S.sub}>
          Editing <span style={{ color: C.magenta, fontFamily: F.mono }}>{marketId}</span>. The
          Gamma-sourced IDs and resolution date are locked — re-add the market to re-fetch those.
          Nothing is written until SAVE.
        </div>

        {state.kind === 'loading' && <div style={S.loading}>loading entry…</div>}

        {state.kind !== 'loading' && (
          <>
            <div style={S.autoBox}>
              <div style={S.autoRow}>
                <span style={S.autoKey}>condition_id</span>
                <span style={S.autoVal}>{locked.conditionId || '—'}</span>
              </div>
              <div style={S.autoRow}>
                <span style={S.autoKey}>resolves</span>
                <span style={S.autoVal}>{locked.resolves || '—'}</span>
              </div>
              <div style={S.autoRow}>
                <span style={S.autoKey}>url</span>
                <span style={S.autoVal}>{locked.url || '—'}</span>
              </div>
            </div>

            <div style={S.grid}>
              <div style={{ ...S.field, gridColumn: '1 / -1' }}>
                <label style={S.label}>NAME *</label>
                <input
                  style={S.input}
                  value={name}
                  spellCheck={false}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div style={S.field}>
                <label style={S.label}>CATEGORY *</label>
                <input
                  style={S.input}
                  value={category}
                  spellCheck={false}
                  onChange={(e) => setCategory(e.target.value)}
                />
              </div>
              <div style={S.field}>
                <label style={S.label}>RULE_KEY *</label>
                <input
                  style={S.input}
                  value={ruleKey}
                  spellCheck={false}
                  onChange={(e) => setRuleKey(e.target.value)}
                />
              </div>
              <div style={S.field}>
                <label style={S.label}>ORACLE_TYPE *</label>
                <input
                  style={S.input}
                  value={oracleType}
                  spellCheck={false}
                  onChange={(e) => setOracleType(e.target.value)}
                />
              </div>
              <div style={S.field}>
                <label style={S.label}>PREFERRED_SIDE *</label>
                <div style={S.sideRow}>
                  {(['YES', 'NO'] as const).map((s) => (
                    <button
                      key={s}
                      style={{ ...S.sideBtn, ...(side === s ? S.sideOn : null) }}
                      onClick={() => setSide(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
              <div style={S.field}>
                <label style={S.label}>THESIS_BUCKET</label>
                <input
                  style={S.input}
                  value={thesisBucket}
                  spellCheck={false}
                  onChange={(e) => setThesisBucket(e.target.value)}
                />
              </div>
              <div style={{ ...S.field, gridColumn: '1 / -1' }}>
                <label style={S.label}>RISK_FLAGS (comma-separated, empty clears)</label>
                <input
                  style={S.input}
                  value={riskFlags}
                  spellCheck={false}
                  onChange={(e) => setRiskFlags(e.target.value)}
                />
              </div>
              <div style={{ ...S.field, gridColumn: '1 / -1' }}>
                <label style={S.label}>NOTES</label>
                <input
                  style={S.input}
                  value={notes}
                  spellCheck={false}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </div>
            </div>
          </>
        )}

        {state.kind === 'error' && <pre style={S.errorBox}>{state.message.slice(0, 1500)}</pre>}

        <div style={S.btnRow}>
          <button
            style={S.btnDanger}
            onClick={() => setState({ kind: 'confirmDelete' })}
            disabled={state.kind === 'loading' || busy}
            title="Remove this market from the registry"
          >
            DELETE
          </button>
          <div style={S.statusLine}>
            {state.kind === 'ready' && !saveReady && (
              <span style={{ color: C.amber }}>fill the * fields to enable SAVE</span>
            )}
            {state.kind === 'ready' && saveReady && (
              <span style={{ color: C.textMute }}>nothing written until SAVE</span>
            )}
            {state.kind === 'confirmDelete' && (
              <span style={{ color: C.red }}>delete {marketId}? this cannot be undone</span>
            )}
            {state.kind === 'saving' && <span style={{ color: C.amber }}>writing…</span>}
            {state.kind === 'deleting' && <span style={{ color: C.amber }}>deleting…</span>}
            {state.kind === 'ok' && (
              <span style={{ color: C.cyan }}>
                ● {state.verb} {marketId}
              </span>
            )}
          </div>
          {state.kind === 'confirmDelete' ? (
            <>
              <button style={S.btnGhost} onClick={() => setState({ kind: 'ready' })}>
                CANCEL
              </button>
              <button style={S.btnDangerSolid} onClick={remove}>
                CONFIRM DELETE ▸
              </button>
            </>
          ) : (
            <>
              <button style={S.btnGhost} onClick={onClose}>
                {state.kind === 'ok' ? 'CLOSE' : 'CANCEL'}
              </button>
              <button
                style={S.btnPrimary}
                onClick={save}
                disabled={!saveReady || busy}
                title={!saveReady ? 'Fill the required (*) fields first' : ''}
              >
                SAVE ▸
              </button>
            </>
          )}
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
    width: 'min(820px, 96vw)',
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
  sub: { fontSize: 11.5, color: C.textDim, lineHeight: 1.55, maxWidth: 760 },
  loading: { fontFamily: F.mono, fontSize: 12, color: C.textMute, padding: '20px 0' },
  autoBox: {
    background: C.bg,
    border: `1px solid ${C.cyan}55`,
    padding: 10,
    display: 'flex',
    flexDirection: 'column',
    gap: 4
  },
  autoRow: { display: 'flex', gap: 10, fontFamily: F.mono, fontSize: 10.5 },
  autoKey: { color: C.textMute, minWidth: 96 },
  autoVal: { color: C.cyan, wordBreak: 'break-all', flex: 1 },
  grid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 },
  field: { display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 },
  label: {
    fontSize: 9.5,
    color: C.textMute,
    fontFamily: F.mono,
    letterSpacing: 0.6,
    fontWeight: 700
  },
  input: {
    background: C.bg,
    color: C.text,
    border: `1px solid ${C.line2}`,
    padding: '7px 9px',
    fontFamily: F.mono,
    fontSize: 11.5,
    outline: 'none'
  },
  sideRow: { display: 'flex', gap: 0 },
  sideBtn: {
    flex: 1,
    background: 'transparent',
    border: `1px solid ${C.line2}`,
    color: C.textDim,
    padding: '7px 0',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer',
    outline: 'none'
  },
  sideOn: {
    color: C.cyan,
    borderColor: C.cyan,
    boxShadow: `inset 0 0 10px ${C.cyan}22`
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
    maxHeight: 200,
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
  btnDanger: {
    background: 'transparent',
    border: `1px solid ${C.red}`,
    color: C.red,
    padding: '8px 14px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none'
  },
  btnDangerSolid: {
    background: C.red,
    color: C.bg,
    border: 'none',
    padding: '8px 16px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.8,
    cursor: 'pointer',
    textTransform: 'uppercase',
    boxShadow: `0 0 14px ${C.red}88`,
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
