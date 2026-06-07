import { useEffect, useState, type CSSProperties } from 'react'
import { usePmDataRefresh } from '../../lib/pmDataContext'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'

// Shape of the JSON printed by `registry-add --preview`.
interface PreviewMarket {
  index: number
  question: string
  condition_id: string | null
}
interface Preview {
  name: string
  polymarket_url: string
  event_slug: string
  suggested_market_id: string
  num_markets: number
  market_index: number
  condition_id: string | null
  yes_token_id: string | null
  no_token_id: string | null
  outcomes: string[]
  resolution_date: string | null
  markets: PreviewMarket[]
}

type State =
  | { kind: 'idle' }
  | { kind: 'fetching' }
  | { kind: 'ready' }
  | { kind: 'committing' }
  | { kind: 'ok' }
  | { kind: 'error'; message: string }

const runErr = (r: { ok: boolean; stderr: string; stdout: string; code: number }): string =>
  r.stderr.trim() || r.stdout.trim() || `exit ${r.code}`

export const AddMarketModal = ({ onClose }: { onClose: () => void }) => {
  const refresh = usePmDataRefresh()
  const [url, setUrl] = useState('')
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [preview, setPreview] = useState<Preview | null>(null)
  const [marketIndex, setMarketIndex] = useState(0)

  // Judgment fields (IDs are auto-filled from Gamma; these need a human).
  const [marketId, setMarketId] = useState('')
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

  const fetchPreview = async (index = 0): Promise<void> => {
    if (!url.trim()) return
    setState({ kind: 'fetching' })
    try {
      const result = await window.pm.runStage('registry-add', [
        '--url',
        url.trim(),
        '--market-index',
        String(index),
        '--preview'
      ])
      if (!result.ok) {
        setState({ kind: 'error', message: runErr(result) })
        return
      }
      const data = JSON.parse(result.stdout) as Preview
      setPreview(data)
      setMarketIndex(data.market_index)
      // Only seed the suggested id on first fetch so we don't clobber edits.
      setMarketId((cur) => cur || data.suggested_market_id)
      setState({ kind: 'ready' })
    } catch (err) {
      setState({ kind: 'error', message: String(err) })
    }
  }

  const commit = async (): Promise<void> => {
    setState({ kind: 'committing' })
    try {
      const args = [
        '--url',
        url.trim(),
        '--market-index',
        String(marketIndex),
        '--market-id',
        marketId.trim(),
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
        notes.trim()
      ]
      for (const flag of riskFlags.split(',').map((f) => f.trim()).filter(Boolean)) {
        args.push('--risk-flag', flag)
      }
      const result = await window.pm.runStage('registry-add', args)
      if (!result.ok) {
        setState({ kind: 'error', message: runErr(result) })
        return
      }
      await refresh()
      setState({ kind: 'ok' })
    } catch (err) {
      setState({ kind: 'error', message: String(err) })
    }
  }

  const commitReady =
    !!preview &&
    !!marketId.trim() &&
    !!category.trim() &&
    !!ruleKey.trim() &&
    !!oracleType.trim()

  return (
    <div style={S.backdrop} onClick={onClose}>
      <div style={S.card} onClick={(e) => e.stopPropagation()}>
        <div style={S.hdr}>// registry-add → market_registry.yaml</div>
        <div style={S.sub}>
          Paste a Polymarket event URL or slug. polyberg fetches the{' '}
          <span style={{ color: C.cyan, fontFamily: F.mono }}>condition_id</span> and both token IDs
          from Gamma; you fill the judgment fields. Nothing is written until ADD.
        </div>

        <div style={S.urlRow}>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            spellCheck={false}
            placeholder="https://polymarket.com/event/…  or  bare-slug"
            style={S.urlInput}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void fetchPreview(0)
            }}
          />
          <button
            style={S.btnSecondary}
            onClick={() => void fetchPreview(0)}
            disabled={!url.trim() || state.kind === 'fetching'}
          >
            {state.kind === 'fetching' ? 'FETCHING…' : 'FETCH IDS'}
          </button>
        </div>

        {preview && (
          <>
            {preview.num_markets > 1 && (
              <div style={S.field}>
                <label style={S.label}>MARKET (event has {preview.num_markets})</label>
                <select
                  style={S.input}
                  value={marketIndex}
                  onChange={(e) => {
                    const idx = Number(e.target.value)
                    setMarketIndex(idx)
                    void fetchPreview(idx)
                  }}
                >
                  {preview.markets.map((m) => (
                    <option key={m.index} value={m.index}>
                      [{m.index}] {m.question}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div style={S.autoBox}>
              <div style={S.autoRow}>
                <span style={S.autoKey}>name</span>
                <span style={S.autoVal}>{preview.name}</span>
              </div>
              <div style={S.autoRow}>
                <span style={S.autoKey}>condition_id</span>
                <span style={S.autoVal}>{preview.condition_id || '—'}</span>
              </div>
              <div style={S.autoRow}>
                <span style={S.autoKey}>yes_token_id</span>
                <span style={S.autoVal}>{preview.yes_token_id || '—'}</span>
              </div>
              <div style={S.autoRow}>
                <span style={S.autoKey}>no_token_id</span>
                <span style={S.autoVal}>{preview.no_token_id || '—'}</span>
              </div>
              <div style={S.autoRow}>
                <span style={S.autoKey}>resolves</span>
                <span style={S.autoVal}>
                  {preview.resolution_date || '—'} · outcomes [{preview.outcomes.join(', ')}]
                </span>
              </div>
            </div>

            <div style={S.grid}>
              <div style={S.field}>
                <label style={S.label}>MARKET_ID *</label>
                <input
                  style={S.input}
                  value={marketId}
                  spellCheck={false}
                  onChange={(e) => setMarketId(e.target.value)}
                  placeholder="lower_snake_case"
                />
              </div>
              <div style={S.field}>
                <label style={S.label}>CATEGORY *</label>
                <input
                  style={S.input}
                  value={category}
                  spellCheck={false}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="core_hormuz"
                />
              </div>
              <div style={S.field}>
                <label style={S.label}>RULE_KEY *</label>
                <input
                  style={S.input}
                  value={ruleKey}
                  spellCheck={false}
                  onChange={(e) => setRuleKey(e.target.value)}
                  placeholder="hormuz_portwatch_7dma"
                />
              </div>
              <div style={S.field}>
                <label style={S.label}>ORACLE_TYPE *</label>
                <input
                  style={S.input}
                  value={oracleType}
                  spellCheck={false}
                  onChange={(e) => setOracleType(e.target.value)}
                  placeholder="IMF Portwatch data"
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
                  placeholder="Iran conflict"
                />
              </div>
              <div style={{ ...S.field, gridColumn: '1 / -1' }}>
                <label style={S.label}>RISK_FLAGS (comma-separated)</label>
                <input
                  style={S.input}
                  value={riskFlags}
                  spellCheck={false}
                  onChange={(e) => setRiskFlags(e.target.value)}
                  placeholder="pure data oracle, low media ambiguity"
                />
              </div>
              <div style={{ ...S.field, gridColumn: '1 / -1' }}>
                <label style={S.label}>NOTES</label>
                <input
                  style={S.input}
                  value={notes}
                  spellCheck={false}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Resolution detail / rule nuance"
                />
              </div>
            </div>
          </>
        )}

        {state.kind === 'error' && <pre style={S.errorBox}>{state.message.slice(0, 1500)}</pre>}

        <div style={S.btnRow}>
          <div style={S.statusLine}>
            {state.kind === 'idle' && (
              <span style={{ color: C.textMute }}>paste a URL, then FETCH IDS</span>
            )}
            {state.kind === 'ready' && !commitReady && (
              <span style={{ color: C.amber }}>fill the * fields to enable ADD</span>
            )}
            {state.kind === 'ready' && commitReady && (
              <span style={{ color: C.textMute }}>ready — nothing written until ADD</span>
            )}
            {state.kind === 'committing' && <span style={{ color: C.amber }}>writing…</span>}
            {state.kind === 'ok' && (
              <span style={{ color: C.cyan }}>● added {marketId} to market_registry.yaml</span>
            )}
          </div>
          <button style={S.btnGhost} onClick={onClose}>
            {state.kind === 'ok' ? 'CLOSE' : 'CANCEL'}
          </button>
          <button
            style={S.btnPrimary}
            onClick={commit}
            disabled={!commitReady || state.kind === 'committing' || state.kind === 'ok'}
            title={!commitReady ? 'Fetch IDs and fill the required (*) fields first' : ''}
          >
            ADD MARKET ▸
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
  urlRow: { display: 'flex', gap: 8 },
  urlInput: {
    flex: 1,
    background: C.bg,
    color: C.text,
    border: `1px solid ${C.line2}`,
    padding: '8px 10px',
    fontFamily: F.mono,
    fontSize: 12,
    outline: 'none'
  },
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
