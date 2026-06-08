import { useEffect, useState, type CSSProperties } from 'react'
import { usePmDataRefresh } from '../../lib/pmDataContext'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'

// Shape of the JSON printed by `registry-add --preview`.
interface PreviewMarket {
  index: number
  question: string
  condition_id: string | null
  group_item_title: string | null
  suggested_market_id: string
  preferred_side: 'YES' | 'NO'
  matched_market_id: string | null
  exists: boolean
}
// Auto-derived judgment fields + per-field provenance (inherited/rules/default).
type FieldSource = 'inherited' | 'rules' | 'default'
interface Suggestion {
  market_id: string
  category: string
  thesis_bucket: string
  rule_key: string
  oracle_type: string
  preferred_side: 'YES' | 'NO'
  risk_flags: string[]
  notes: string
  rule_risk: Record<string, unknown> | null
  sources: Record<string, FieldSource>
  matched_market_id: string | null
  match_score: number
}
interface Preview {
  name: string
  polymarket_url: string
  event_slug: string
  resolution_source: string | null
  tags: string[]
  suggested_market_id: string
  num_markets: number
  market_index: number
  condition_id: string | null
  yes_token_id: string | null
  no_token_id: string | null
  outcomes: string[]
  resolution_date: string | null
  description: string | null
  group_item_title: string | null
  suggestion: Suggestion
  markets: PreviewMarket[]
}

// Shape of the JSON printed by `registry-add --all`.
interface BatchResult {
  added: string[]
  skipped: { market_id: string; reason: string }[]
  failed: { market_id: string; error: string }[]
  path: string
}

type State =
  | { kind: 'idle' }
  | { kind: 'fetching' }
  | { kind: 'ready' }
  | { kind: 'committing' }
  | { kind: 'ok' }
  | { kind: 'batchDone'; result: BatchResult }
  | { kind: 'error'; message: string }

const runErr = (r: { ok: boolean; stderr: string; stdout: string; code: number }): string =>
  r.stderr.trim() || r.stdout.trim() || `exit ${r.code}`

const SRC_LABEL: Record<FieldSource, string> = {
  inherited: 'auto · from existing market',
  rules: 'auto · from resolution rules',
  default: 'guess · please review'
}
const SRC_COLOR: Record<FieldSource, string> = {
  inherited: C.cyan,
  rules: C.amber,
  default: C.textMute
}

// Tiny provenance chip shown next to an auto-prefilled field's label.
const SourceBadge = ({ src }: { src?: FieldSource }) => {
  if (!src) return null
  const c = SRC_COLOR[src]
  return (
    <span
      title={SRC_LABEL[src]}
      style={{
        marginLeft: 6,
        fontSize: 8,
        fontWeight: 700,
        letterSpacing: 0.4,
        color: c,
        border: `1px solid ${c}66`,
        borderRadius: 2,
        padding: '0 4px',
        textTransform: 'uppercase'
      }}
    >
      {src === 'default' ? 'guess' : 'auto'}
    </span>
  )
}

export const AddMarketModal = ({ onClose }: { onClose: () => void }) => {
  const refresh = usePmDataRefresh()
  const [url, setUrl] = useState('')
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [preview, setPreview] = useState<Preview | null>(null)
  const [marketIndex, setMarketIndex] = useState(0)

  // Judgment fields — prefilled from the auto-parse suggestion; user reviews.
  const [marketId, setMarketId] = useState('')
  const [category, setCategory] = useState('')
  const [ruleKey, setRuleKey] = useState('')
  const [oracleType, setOracleType] = useState('')
  const [side, setSide] = useState<'YES' | 'NO'>('NO')
  const [thesisBucket, setThesisBucket] = useState('')
  const [notes, setNotes] = useState('')
  const [riskFlags, setRiskFlags] = useState('')
  // Provenance badges + the suggested rule_risk block we pass through on commit.
  const [sources, setSources] = useState<Record<string, FieldSource>>({})
  const [ruleRisk, setRuleRisk] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Load a market's auto-suggested judgment fields into the form. Runs on the
  // first fetch and on every bracket switch — switching brackets is an explicit
  // "load this market" intent, so re-prefilling (overwriting prior edits) is
  // expected. Nothing is written until the user clicks ADD.
  const applySuggestion = (s: Suggestion): void => {
    setMarketId(s.market_id)
    setCategory(s.category)
    setRuleKey(s.rule_key)
    setOracleType(s.oracle_type)
    setSide(s.preferred_side)
    setThesisBucket(s.thesis_bucket)
    setNotes(s.notes)
    setRiskFlags(s.risk_flags.join(', '))
    setSources(s.sources)
    setRuleRisk(s.rule_risk)
  }

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
      applySuggestion(data.suggestion)
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
      // Preserve the suggested rule_risk block unless the user cleared the form.
      if (ruleRisk) args.push('--rule-risk-json', JSON.stringify(ruleRisk))
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

  // Batch path: add every bracket of the event using its auto-suggestion. The
  // backend skips brackets already in the registry (by id or condition_id).
  const commitAll = async (): Promise<void> => {
    setState({ kind: 'committing' })
    try {
      const result = await window.pm.runStage('registry-add', ['--url', url.trim(), '--all'])
      // --all exits non-zero only if some brackets *failed*; partial success
      // still prints the JSON summary on stdout, so parse before bailing.
      let parsed: BatchResult | null = null
      try {
        parsed = JSON.parse(result.stdout) as BatchResult
      } catch {
        parsed = null
      }
      if (!parsed) {
        setState({ kind: 'error', message: runErr(result) })
        return
      }
      await refresh()
      setState({ kind: 'batchDone', result: parsed })
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
          <span style={{ color: C.cyan, fontFamily: F.mono }}>condition_id</span> + token IDs from
          Gamma and <span style={{ color: C.cyan }}>auto-suggests the judgment fields</span> from the
          resolution rules and your existing markets (<SourceBadge src="inherited" /> from a sibling
          market · <SourceBadge src="rules" /> from the rules · <SourceBadge src="default" /> a guess).
          Review and edit, then ADD. Nothing is written until you commit.
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
              {preview.resolution_source && (
                <div style={S.autoRow}>
                  <span style={S.autoKey}>source</span>
                  <span style={S.autoVal}>{preview.resolution_source}</span>
                </div>
              )}
              {preview.tags.length > 0 && (
                <div style={S.autoRow}>
                  <span style={S.autoKey}>tags</span>
                  <span style={S.autoVal}>{preview.tags.join(' · ')}</span>
                </div>
              )}
              {preview.suggestion.matched_market_id && (
                <div style={S.autoRow}>
                  <span style={S.autoKey}>matched</span>
                  <span style={{ ...S.autoVal, color: C.amber }}>
                    judgment fields inherited from {preview.suggestion.matched_market_id}
                  </span>
                </div>
              )}
            </div>

            {preview.description && (
              <div style={S.field}>
                <label style={S.label}>RESOLUTION RULES (from Polymarket)</label>
                <pre style={S.rulesBox}>{preview.description}</pre>
              </div>
            )}

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
                <label style={S.label}>
                  CATEGORY *<SourceBadge src={sources.category} />
                </label>
                <input
                  style={S.input}
                  value={category}
                  spellCheck={false}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="core_hormuz"
                />
              </div>
              <div style={S.field}>
                <label style={S.label}>
                  RULE_KEY *<SourceBadge src={sources.rule_key} />
                </label>
                <input
                  style={S.input}
                  value={ruleKey}
                  spellCheck={false}
                  onChange={(e) => setRuleKey(e.target.value)}
                  placeholder="hormuz_portwatch_7dma"
                />
              </div>
              <div style={S.field}>
                <label style={S.label}>
                  ORACLE_TYPE *<SourceBadge src={sources.oracle_type} />
                </label>
                <input
                  style={S.input}
                  value={oracleType}
                  spellCheck={false}
                  onChange={(e) => setOracleType(e.target.value)}
                  placeholder="IMF Portwatch data"
                />
              </div>
              <div style={S.field}>
                <label style={S.label}>
                  PREFERRED_SIDE *<SourceBadge src={sources.preferred_side} />
                </label>
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
                <label style={S.label}>
                  THESIS_BUCKET<SourceBadge src={sources.thesis_bucket} />
                </label>
                <input
                  style={S.input}
                  value={thesisBucket}
                  spellCheck={false}
                  onChange={(e) => setThesisBucket(e.target.value)}
                  placeholder="Iran conflict"
                />
              </div>
              <div style={{ ...S.field, gridColumn: '1 / -1' }}>
                <label style={S.label}>
                  RISK_FLAGS (comma-separated)<SourceBadge src={sources.risk_flags} />
                </label>
                <input
                  style={S.input}
                  value={riskFlags}
                  spellCheck={false}
                  onChange={(e) => setRiskFlags(e.target.value)}
                  placeholder="pure data oracle, low media ambiguity"
                />
              </div>
              <div style={{ ...S.field, gridColumn: '1 / -1' }}>
                <label style={S.label}>
                  NOTES<SourceBadge src={sources.notes} />
                </label>
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

        {state.kind === 'batchDone' && (
          <pre style={S.batchBox}>
            {`added ${state.result.added.length} · skipped ${state.result.skipped.length} · failed ${state.result.failed.length}\n`}
            {state.result.added.map((m) => `  + ${m}`).join('\n')}
            {state.result.added.length && (state.result.skipped.length || state.result.failed.length)
              ? '\n'
              : ''}
            {state.result.skipped.map((s) => `  · skip ${s.market_id} (${s.reason})`).join('\n')}
            {state.result.skipped.length && state.result.failed.length ? '\n' : ''}
            {state.result.failed.map((f) => `  ✗ ${f.market_id} — ${f.error}`).join('\n')}
          </pre>
        )}

        <div style={S.btnRow}>
          <div style={S.statusLine}>
            {state.kind === 'idle' && (
              <span style={{ color: C.textMute }}>paste a URL, then FETCH IDS</span>
            )}
            {state.kind === 'ready' && !commitReady && (
              <span style={{ color: C.amber }}>fill the * fields to enable ADD</span>
            )}
            {state.kind === 'ready' && commitReady && (
              <span style={{ color: C.textMute }}>review the auto-fill — nothing written until ADD</span>
            )}
            {state.kind === 'committing' && <span style={{ color: C.amber }}>writing…</span>}
            {state.kind === 'ok' && (
              <span style={{ color: C.cyan }}>● added {marketId} to market_registry.yaml</span>
            )}
            {state.kind === 'batchDone' && (
              <span style={{ color: C.cyan }}>● batch done — see summary above</span>
            )}
          </div>
          <button style={S.btnGhost} onClick={onClose}>
            {state.kind === 'ok' || state.kind === 'batchDone' ? 'CLOSE' : 'CANCEL'}
          </button>
          {preview && preview.num_markets > 1 && (
            <button
              style={S.btnSecondary}
              onClick={commitAll}
              disabled={state.kind === 'committing'}
              title="Add every bracket using auto-suggested judgment fields (skips ones already in the registry)"
            >
              ADD ALL {preview.num_markets} ▸
            </button>
          )}
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
  rulesBox: {
    background: C.bg,
    border: `1px solid ${C.line2}`,
    padding: 10,
    fontSize: 10.5,
    fontFamily: F.mono,
    lineHeight: 1.5,
    color: C.textDim,
    margin: 0,
    whiteSpace: 'pre-wrap',
    maxHeight: 150,
    overflowY: 'auto'
  },
  batchBox: {
    background: C.bg,
    border: `1px solid ${C.cyan}55`,
    padding: 12,
    fontSize: 11,
    fontFamily: F.mono,
    lineHeight: 1.6,
    color: C.text,
    margin: 0,
    whiteSpace: 'pre-wrap',
    maxHeight: 220,
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
