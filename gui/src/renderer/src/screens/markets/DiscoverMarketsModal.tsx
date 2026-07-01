import { useEffect, useState, type CSSProperties } from 'react'
import { usePmDataRefresh } from '../../lib/pmDataContext'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'

// Shape of one row from `search-markets` (see registry_discover.discover_events).
interface DiscoverResult {
  event_slug: string | null
  name: string | null
  polymarket_url: string | null
  volume: number | null
  volume_24hr: number | null
  liquidity: number | null
  end_date: string | null
  closed: boolean
  num_markets: number
  tags: string[]
  condition_ids: string[]
  existing_market_count: number
  new_market_count: number
  in_registry: boolean
}

// Shape of the JSON printed by `registry-add --all` (mirrors AddMarketModal).
interface BatchResult {
  added: string[]
  skipped: { market_id: string; reason: string }[]
  failed: { market_id: string; error: string }[]
  path: string
}

type State =
  | { kind: 'idle' }
  | { kind: 'searching' }
  | { kind: 'results' }
  | { kind: 'adding'; done: number; total: number }
  | { kind: 'added'; added: number; skipped: number; failed: number }
  | { kind: 'error'; message: string }

const runErr = (r: { ok: boolean; stderr: string; stdout: string; code: number }): string =>
  r.stderr.trim() || r.stdout.trim() || `exit ${r.code}`

const fmtVol = (v: number | null): string => {
  if (!v) return '—'
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}k`
  return `$${v.toFixed(0)}`
}

export const DiscoverMarketsModal = ({ onClose }: { onClose: () => void }) => {
  const refresh = usePmDataRefresh()
  const [query, setQuery] = useState('')
  const [tag, setTag] = useState('')
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [results, setResults] = useState<DiscoverResult[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const search = async (): Promise<void> => {
    if (!query.trim() && !tag.trim()) return
    setState({ kind: 'searching' })
    setSelected(new Set())
    const args = ['--limit', '30']
    if (query.trim()) args.push('--query', query.trim())
    else if (tag.trim()) args.push('--tag', tag.trim())
    try {
      const result = await window.pm.runStage('search-markets', args)
      if (!result.ok) {
        setState({ kind: 'error', message: runErr(result) })
        return
      }
      const data = JSON.parse(result.stdout) as { results: DiscoverResult[] }
      const rows = data.results.filter((r): r is DiscoverResult => !!r.event_slug)
      setResults(rows)
      // Pre-select events that have at least one bracket not yet in the registry.
      setSelected(new Set(rows.filter((r) => r.new_market_count > 0).map((r) => r.event_slug!)))
      setState({ kind: 'results' })
    } catch (err) {
      setState({ kind: 'error', message: String(err) })
    }
  }

  const toggle = (slug: string): void => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(slug)) next.delete(slug)
      else next.add(slug)
      return next
    })
  }

  // Add every selected event via the existing bulk-add path. registry-add --all
  // auto-suggests judgment fields per bracket and skips ones already tracked, so
  // re-adding a partially-tracked event only lands the genuinely new brackets.
  const addSelected = async (): Promise<void> => {
    const slugs = results.filter((r) => selected.has(r.event_slug!)).map((r) => r.event_slug!)
    if (slugs.length === 0) return
    let added = 0
    let skipped = 0
    let failed = 0
    for (let i = 0; i < slugs.length; i++) {
      setState({ kind: 'adding', done: i, total: slugs.length })
      try {
        const result = await window.pm.runStage('registry-add', ['--url', slugs[i], '--all'])
        let parsed: BatchResult | null = null
        try {
          parsed = JSON.parse(result.stdout) as BatchResult
        } catch {
          parsed = null
        }
        if (parsed) {
          added += parsed.added.length
          skipped += parsed.skipped.length
          failed += parsed.failed.length
        } else {
          failed += 1
        }
      } catch {
        failed += 1
      }
    }
    await refresh()
    setState({ kind: 'added', added, skipped, failed })
  }

  const selectedCount = selected.size
  const busy = state.kind === 'searching' || state.kind === 'adding'

  return (
    <div style={S.backdrop} onClick={onClose}>
      <div style={S.card} onClick={(e) => e.stopPropagation()}>
        <div style={S.hdr}>// search-markets → Polymarket discovery</div>
        <div style={S.sub}>
          Search Polymarket by keyword (or browse a tag) and bulk-add the events you want. Each pick
          runs <span style={{ color: C.cyan, fontFamily: F.mono }}>registry-add --all</span>, which
          auto-suggests judgment fields and skips brackets already in your registry.
        </div>

        <div style={S.searchRow}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            spellCheck={false}
            placeholder="keyword (e.g. hormuz, iran nuclear)"
            style={S.input}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void search()
            }}
          />
          <input
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            spellCheck={false}
            placeholder="or tag slug (e.g. iran)"
            style={{ ...S.input, maxWidth: 200 }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void search()
            }}
          />
          <button
            style={S.btnSecondary}
            onClick={() => void search()}
            disabled={(!query.trim() && !tag.trim()) || busy}
          >
            {state.kind === 'searching' ? 'SEARCHING…' : 'SEARCH'}
          </button>
        </div>

        {state.kind === 'error' && <pre style={S.errorBox}>{state.message.slice(0, 1200)}</pre>}

        {results.length > 0 && (
          <div style={S.resultsBox}>
            {results.map((r) => {
              const checked = selected.has(r.event_slug!)
              const fullyTracked = r.in_registry && r.new_market_count === 0
              return (
                <div
                  key={r.event_slug}
                  style={{ ...S.row, opacity: fullyTracked ? 0.6 : 1 }}
                  onClick={() => toggle(r.event_slug!)}
                >
                  <input type="checkbox" checked={checked} readOnly style={S.check} />
                  <div style={S.rowMain}>
                    <div style={S.rowTitle}>{r.name}</div>
                    <div style={S.rowMeta}>
                      <span style={{ color: C.cyan }}>{fmtVol(r.volume)}</span>
                      <span style={S.metaDim}>· closes {r.end_date || '—'}</span>
                      <span style={S.metaDim}>· {r.num_markets} mkt{r.num_markets === 1 ? '' : 's'}</span>
                      {r.tags.slice(0, 3).map((t) => (
                        <span key={t} style={S.tagChip}>
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div style={S.rowFlag}>
                    {fullyTracked ? (
                      <span style={{ color: C.textMute }}>IN REGISTRY</span>
                    ) : r.in_registry ? (
                      <span style={{ color: C.amber }}>+{r.new_market_count} NEW</span>
                    ) : (
                      <span style={{ color: C.cyan }}>NEW</span>
                    )}
                  </div>
                  {r.polymarket_url && (
                    <button
                      style={S.linkBtn}
                      title={`open ${r.polymarket_url}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        void window.pm.openExternal(r.polymarket_url!)
                      }}
                    >
                      ↗
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {state.kind === 'results' && results.length === 0 && (
          <div style={S.empty}>no events found — try a different keyword or tag</div>
        )}

        <div style={S.btnRow}>
          <div style={S.statusLine}>
            {state.kind === 'idle' && (
              <span style={{ color: C.textMute }}>enter a keyword or tag, then SEARCH</span>
            )}
            {state.kind === 'results' && (
              <span style={{ color: C.textMute }}>
                {selectedCount} selected · click rows to toggle
              </span>
            )}
            {state.kind === 'adding' && (
              <span style={{ color: C.amber }}>
                adding {state.done + 1}/{state.total}…
              </span>
            )}
            {state.kind === 'added' && (
              <span style={{ color: C.cyan }}>
                ● added {state.added} · skipped {state.skipped}
                {state.failed > 0 ? ` · failed ${state.failed}` : ''}
              </span>
            )}
          </div>
          <button style={S.btnGhost} onClick={onClose}>
            {state.kind === 'added' ? 'CLOSE' : 'CANCEL'}
          </button>
          <button
            style={{
              ...S.btnPrimary,
              opacity: selectedCount > 0 && !busy ? 1 : 0.4,
              cursor: selectedCount > 0 && !busy ? 'pointer' : 'not-allowed'
            }}
            onClick={() => void addSelected()}
            disabled={selectedCount === 0 || busy}
          >
            ADD SELECTED ({selectedCount}) ▸
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
    width: 'min(860px, 96vw)',
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
  sub: { fontSize: 11.5, color: C.textDim, lineHeight: 1.55, maxWidth: 800 },
  searchRow: { display: 'flex', gap: 8 },
  input: {
    flex: 1,
    background: C.bg,
    color: C.text,
    border: `1px solid ${C.line2}`,
    padding: '8px 10px',
    fontFamily: F.mono,
    fontSize: 12,
    outline: 'none'
  },
  resultsBox: {
    background: C.bg,
    border: `1px solid ${C.line2}`,
    maxHeight: '52vh',
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column'
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '8px 10px',
    borderBottom: `1px solid ${C.line2}`,
    cursor: 'pointer'
  },
  check: { accentColor: C.magenta, cursor: 'pointer', flexShrink: 0 },
  rowMain: { flex: 1, minWidth: 0 },
  rowTitle: {
    fontSize: 12,
    color: C.text,
    fontFamily: F.body,
    marginBottom: 3,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap'
  },
  rowMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    flexWrap: 'wrap',
    fontFamily: F.mono,
    fontSize: 10
  },
  metaDim: { color: C.textMute },
  tagChip: {
    color: C.textDim,
    border: `1px solid ${C.line}`,
    borderRadius: 2,
    padding: '0 4px',
    fontSize: 8.5,
    textTransform: 'uppercase',
    letterSpacing: 0.3
  },
  rowFlag: {
    fontFamily: F.mono,
    fontSize: 9.5,
    fontWeight: 700,
    letterSpacing: 0.4,
    minWidth: 64,
    textAlign: 'right',
    flexShrink: 0
  },
  linkBtn: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '2px 7px',
    fontFamily: F.mono,
    fontSize: 11,
    cursor: 'pointer',
    flexShrink: 0,
    outline: 'none'
  },
  empty: {
    border: `1px dashed ${C.line}`,
    padding: 20,
    color: C.textMute,
    fontFamily: F.mono,
    fontSize: 11.5,
    textAlign: 'center'
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
    maxHeight: 160,
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
    textTransform: 'uppercase',
    boxShadow: `0 0 14px ${C.magenta}88`,
    outline: 'none'
  }
}
