import { useMemo, useState, type CSSProperties } from 'react'
import { usePmData } from '../../lib/pmDataContext'
import { useLocalState } from '../../lib/useLocalState'
import { colors as C, fonts as F } from '../../styles/tokens'
import type { IntakeItem, IntakeKind, IntakeStatus } from '../../lib/types'

const KINDS: IntakeKind[] = ['tweet', 'article', 'note']

const nowStamp = (): string => {
  const d = new Date()
  return d.toISOString().slice(0, 16).replace('T', ' ') + 'Z'
}

const kindIconFor = (k: IntakeKind): string =>
  k === 'tweet' ? '𝕏' : k === 'article' ? '▤' : '✎'

const statusDot = (s: IntakeStatus): string =>
  s === 'confirmed' ? C.cyan : s === 'rejected' ? C.textMute : C.amber

export const IntakeScreen = () => {
  const pmData = usePmData()
  const [items, setItems] = useLocalState<IntakeItem[]>('polyberg:intake.queue', pmData.intake)
  const [text, setText] = useState('')
  const [author, setAuthor] = useState('')
  const [kind, setKind] = useState<IntakeKind>('tweet')
  const [showRebuild, setShowRebuild] = useState(false)

  const suggestion = useMemo(() => pmData.suggestMarket(text), [text])

  const add = (): void => {
    if (!text.trim()) return
    const it: IntakeItem = {
      id: 'in-' + Math.floor(Math.random() * 9000 + 1000),
      kind,
      addedAt: nowStamp(),
      author: author || (kind === 'note' ? 'me' : '—'),
      url: '',
      text,
      suggestedMarket: suggestion.id,
      suggestionConfidence: suggestion.confidence,
      status: 'suggested'
    }
    setItems([it, ...items])
    setText('')
    setAuthor('')
  }

  const setStatus = (id: string, status: IntakeStatus): void => {
    setItems(items.map((i) => (i.id === id ? { ...i, status } : i)))
  }
  const retag = (id: string, marketId: string): void => {
    setItems(
      items.map((i) =>
        i.id === id
          ? { ...i, suggestedMarket: marketId, suggestionConfidence: 1.0, status: 'confirmed' }
          : i
      )
    )
  }
  const remove = (id: string): void => {
    setItems(items.filter((i) => i.id !== id))
  }

  const confirmed = items.filter((i) => i.status === 'confirmed')
  const suggested = items.filter((i) => i.status === 'suggested')
  const rejected = items.filter((i) => i.status === 'rejected')

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.h1}>INTAKE / CONTEXT REBUILDER</div>
          <div style={S.h1Sub}>
            // paste tweets, articles, notes — auto-tagged to market — rebuild appends to
            recent_catalysts.md
          </div>
        </div>
        <div style={S.headerStats}>
          <Stat k="LOADED" v={items.length} />
          <Stat k="CONFIRMED" v={confirmed.length} accent={C.cyan} />
          <Stat k="PENDING" v={suggested.length} accent={C.amber} />
          <Stat k="REJECTED" v={rejected.length} accent={C.textMute} />
        </div>
      </div>

      <div style={S.body}>
        <div style={S.pastePanel}>
          <div style={S.panelHdr}>// paste new item</div>
          <div style={S.kindRow}>
            {KINDS.map((k) => (
              <button
                key={k}
                onClick={() => setKind(k)}
                style={{ ...S.kindBtn, ...(kind === k ? S.kindBtnOn : null) }}
              >
                {k.toUpperCase()}
              </button>
            ))}
            <div style={{ flex: 1 }} />
            <input
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="@handle / source"
              style={S.input}
            />
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="paste tweet text, article summary, or note here…"
            style={S.textarea}
          />
          <div style={S.pasteFoot}>
            <div style={{ flex: 1 }}>
              {text.length > 0 && suggestion.id ? (
                <div style={S.suggestion}>
                  <span style={S.suggLabel}>SUGGESTED MARKET</span>
                  <span style={{ ...S.suggChip, color: C.magenta, borderColor: C.magenta }}>
                    {suggestion.id}
                  </span>
                  <span style={S.suggConf}>
                    {(suggestion.confidence * 100).toFixed(0)}% conf
                  </span>
                </div>
              ) : text.length > 0 ? (
                <div style={{ ...S.suggestion, color: C.amber }}>
                  <span style={S.suggLabel}>NO MATCH</span>
                  <span style={{ fontFamily: F.mono, fontSize: 10.5 }}>
                    tag manually after add
                  </span>
                </div>
              ) : (
                <div style={S.suggLabel}>awaiting input…</div>
              )}
            </div>
            <button
              style={S.btnGhost}
              onClick={() => {
                setText('')
                setAuthor('')
              }}
            >
              CLEAR
            </button>
            <button
              style={{ ...S.btnPrimary, opacity: text.trim() ? 1 : 0.4 }}
              onClick={add}
            >
              + ADD TO QUEUE ▸
            </button>
          </div>
        </div>

        <div style={S.queuePanel}>
          <div style={S.panelHdr}>
            // loaded queue · {items.length} items
            <span style={{ flex: 1 }} />
            <span style={S.legend}>
              <span style={{ color: C.amber }}>● </span>SUGGESTED
            </span>
            <span style={S.legend}>
              <span style={{ color: C.cyan }}>● </span>CONFIRMED
            </span>
            <span style={S.legend}>
              <span style={{ color: C.textMute }}>● </span>REJECTED
            </span>
          </div>
          <div style={S.queueList}>
            {items.map((it) => (
              <QueueRow
                key={it.id}
                it={it}
                onConfirm={() => setStatus(it.id, 'confirmed')}
                onReject={() => setStatus(it.id, 'rejected')}
                onRemove={() => remove(it.id)}
                onRetag={(mid) => retag(it.id, mid)}
              />
            ))}
          </div>
        </div>

        <div style={S.footer}>
          <div style={S.warnLine}>
            <span style={{ color: C.amber, textShadow: `0 0 6px ${C.amber}66` }}>⚠</span>
            <span>
              diff is shown before any file is written. nothing executes. rebuild appends to{' '}
              <span style={{ color: C.magenta }}>recent_catalysts.md</span> + updates live_state
              thesis if changed.
            </span>
          </div>
          <button
            style={{
              ...S.btnPrimary,
              padding: '10px 20px',
              fontSize: 12,
              opacity: confirmed.length === 0 ? 0.4 : 1
            }}
            onClick={() => setShowRebuild(true)}
            disabled={confirmed.length === 0}
          >
            REBUILD CONTEXT · {confirmed.length} CONFIRMED ▸
          </button>
        </div>
      </div>

      {showRebuild ? (
        <RebuildModal items={confirmed} onClose={() => setShowRebuild(false)} />
      ) : null}
    </div>
  )
}

const Stat = ({ k, v, accent }: { k: string; v: number; accent?: string }) => (
  <div style={S.stat}>
    <div style={S.statK}>{k}</div>
    <div
      style={{
        ...S.statV,
        color: accent || C.text,
        textShadow: accent ? `0 0 8px ${accent}66` : 'none'
      }}
    >
      {v}
    </div>
  </div>
)

const QueueRow = ({
  it,
  onConfirm,
  onReject,
  onRemove,
  onRetag
}: {
  it: IntakeItem
  onConfirm: () => void
  onReject: () => void
  onRemove: () => void
  onRetag: (mid: string) => void
}) => {
  const pmData = usePmData()
  const m = it.suggestedMarket ? pmData.marketById(it.suggestedMarket) : undefined
  const dot = statusDot(it.status)
  const [editingTag, setEditingTag] = useState(false)
  return (
    <div
      style={{
        ...S.qRow,
        borderLeftColor: dot,
        opacity: it.status === 'rejected' ? 0.5 : 1
      }}
    >
      <div style={{ ...S.qDot, background: dot, boxShadow: `0 0 6px ${dot}` }} />
      <div style={S.qKind}>
        <span style={S.qKindIcon}>{kindIconFor(it.kind)}</span>
        <span style={S.qKindLabel}>{it.kind.toUpperCase()}</span>
      </div>
      <div style={S.qMain}>
        <div style={S.qMeta}>
          <span style={{ color: C.text, fontWeight: 600 }}>{it.author}</span>
          <span style={{ color: C.textMute }}>·</span>
          <span style={{ color: C.textMute }}>{it.addedAt}</span>
          {it.url ? <span style={{ color: C.textMute }}>· {it.url}</span> : null}
        </div>
        <div style={S.qText}>{it.text}</div>
      </div>
      <div style={S.qSugg}>
        <div style={S.qSuggK}>SUGGESTED</div>
        {editingTag ? (
          <select
            value={it.suggestedMarket || ''}
            onChange={(e) => {
              if (e.target.value) onRetag(e.target.value)
              setEditingTag(false)
            }}
            style={S.select}
          >
            <option value="">— none —</option>
            {pmData.markets.map((mm) => (
              <option key={mm.id} value={mm.id}>
                {mm.id}
              </option>
            ))}
          </select>
        ) : m ? (
          <div
            onClick={() => setEditingTag(true)}
            style={{
              ...S.qSuggChip,
              color: C.magenta,
              borderColor: C.magenta,
              cursor: 'pointer'
            }}
          >
            {m.id}
            <span style={S.qSuggConf}>{(it.suggestionConfidence * 100).toFixed(0)}%</span>
          </div>
        ) : (
          <div
            onClick={() => setEditingTag(true)}
            style={{
              ...S.qSuggChip,
              color: C.amber,
              borderColor: C.amber,
              cursor: 'pointer'
            }}
          >
            UNTAGGED · click to set
          </div>
        )}
      </div>
      <div style={S.qActions}>
        {it.status !== 'confirmed' ? (
          <button style={S.qBtnConfirm} onClick={onConfirm}>
            ✓ CONFIRM
          </button>
        ) : null}
        {it.status !== 'rejected' ? (
          <button style={S.qBtnReject} onClick={onReject}>
            ✕ REJECT
          </button>
        ) : null}
        <button style={S.qBtnDel} onClick={onRemove} title="remove">
          ✕
        </button>
      </div>
    </div>
  )
}

const RebuildModal = ({
  items,
  onClose
}: {
  items: IntakeItem[]
  onClose: () => void
}) => {
  const pmData = usePmData()
  const byMarket: Record<string, IntakeItem[]> = {}
  items.forEach((it) => {
    const k = it.suggestedMarket || '__untagged'
    ;(byMarket[k] = byMarket[k] || []).push(it)
  })
  return (
    <div style={S.modalOverlay} onClick={onClose}>
      <div style={S.modal} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalHdr}>
          <div>
            <div style={S.h1}>REBUILD · DIFF PREVIEW</div>
            <div style={S.h1Sub}>// no files written until you approve</div>
          </div>
          <button style={S.btnGhost} onClick={onClose}>
            ✕ CANCEL
          </button>
        </div>

        <div style={S.modalBody}>
          <div style={S.diffSubhdr}>// recent_catalysts.md · proposed appends</div>
          {Object.entries(byMarket).map(([mid, list]) => {
            const m = mid === '__untagged' ? undefined : pmData.marketById(mid)
            return (
              <div key={mid} style={S.diffMarket}>
                <div style={S.diffMarketHdr}>
                  <span style={{ color: C.magenta, textShadow: `0 0 4px ${C.magenta}` }}>
                    ## {mid}
                  </span>
                  <span style={{ color: C.textDim, marginLeft: 8 }}>
                    {m ? m.name : 'untagged'}
                  </span>
                  <span
                    style={{
                      marginLeft: 'auto',
                      color: C.cyan,
                      fontFamily: F.mono,
                      fontSize: 10.5
                    }}
                  >
                    +{list.length} ENTRIES
                  </span>
                </div>
                <pre style={S.diffPre}>
                  {list
                    .map(
                      (it) =>
                        `+ ${it.addedAt} · ${it.author} (${it.kind})\n+   ${it.text.slice(0, 220)}${
                          it.text.length > 220 ? '…' : ''
                        }\n`
                    )
                    .join('\n')}
                </pre>
              </div>
            )
          })}

          <div style={{ ...S.diffSubhdr, marginTop: 18 }}>
            // live_state.yaml thesis · no changes proposed
          </div>
          <div style={S.diffNoChange}>= thesis unchanged · constraints unchanged</div>

          <div style={{ ...S.diffSubhdr, marginTop: 14 }}>
            // project instructions · no changes proposed
          </div>
          <div style={S.diffNoChange}>= context/instructions.md unchanged</div>
        </div>

        <div style={S.modalFoot}>
          <span style={{ ...S.warnLine, flex: 1 }}>
            <span style={{ color: C.amber }}>⚠</span>
            <span>
              writing {items.length} entries to{' '}
              <span style={{ color: C.magenta }}>recent_catalysts.md</span> · proceeds to next
              workflow stage on success
            </span>
          </span>
          <button style={S.btnGhost} onClick={onClose}>
            CANCEL
          </button>
          <button style={{ ...S.btnPrimary, padding: '8px 18px' }} onClick={onClose}>
            WRITE & ADVANCE ▸
          </button>
        </div>
      </div>
    </div>
  )
}

const S: Record<string, CSSProperties> = {
  root: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
    padding: 18,
    gap: 14,
    overflow: 'auto'
  },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 16
  },
  h1: {
    fontSize: 18,
    fontWeight: 700,
    fontFamily: F.display,
    letterSpacing: 1,
    color: C.text
  },
  h1Sub: {
    fontSize: 11,
    color: C.textDim,
    fontFamily: F.mono,
    marginTop: 3,
    letterSpacing: 0.4
  },
  headerStats: { display: 'flex', gap: 20 },
  stat: { display: 'flex', flexDirection: 'column', alignItems: 'flex-end' },
  statK: {
    fontSize: 10,
    color: C.textDim,
    fontFamily: F.mono,
    letterSpacing: 1,
    fontWeight: 600
  },
  statV: {
    fontSize: 22,
    fontFamily: F.mono,
    fontWeight: 700,
    marginTop: 2,
    letterSpacing: -0.5
  },

  body: { flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 },

  pastePanel: { background: C.bgPanel, border: `1px solid ${C.line}`, padding: 14 },
  panelHdr: {
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 0.8,
    fontWeight: 700,
    fontFamily: F.mono,
    marginBottom: 10,
    textShadow: `0 0 4px ${C.magenta}66`,
    display: 'flex',
    alignItems: 'center',
    gap: 14
  },
  kindRow: { display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8 },
  kindBtn: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.textDim,
    padding: '5px 12px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer'
  },
  kindBtnOn: {
    background: C.magentaSft,
    border: `1px solid ${C.magenta}`,
    color: C.magenta,
    textShadow: `0 0 6px ${C.magenta}66`
  },
  input: {
    background: C.bgInput,
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '5px 10px',
    fontFamily: F.mono,
    fontSize: 11,
    width: 220,
    outline: 'none'
  },
  textarea: {
    width: '100%',
    minHeight: 100,
    background: C.bgInput,
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: 12,
    fontFamily: F.body,
    fontSize: 13,
    lineHeight: 1.5,
    resize: 'vertical',
    outline: 'none',
    boxSizing: 'border-box'
  },
  pasteFoot: { display: 'flex', gap: 10, marginTop: 10, alignItems: 'center' },
  suggestion: { display: 'flex', gap: 10, alignItems: 'center' },
  suggLabel: {
    fontSize: 10,
    color: C.textDim,
    fontFamily: F.mono,
    letterSpacing: 0.6,
    fontWeight: 600
  },
  suggChip: {
    padding: '3px 8px',
    border: '1px solid',
    fontSize: 10.5,
    fontFamily: F.mono,
    fontWeight: 700,
    letterSpacing: 0.4
  },
  suggConf: {
    fontSize: 10.5,
    color: C.cyan,
    fontFamily: F.mono,
    letterSpacing: 0.4
  },

  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '6px 14px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase'
  },
  btnPrimary: {
    background: C.magenta,
    color: C.bg,
    border: 'none',
    padding: '6px 16px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 0.8,
    cursor: 'pointer',
    textTransform: 'uppercase',
    boxShadow: `0 0 12px ${C.magenta}88`
  },

  queuePanel: {
    background: C.bgPanel,
    border: `1px solid ${C.line}`,
    padding: 14,
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0
  },
  legend: {
    fontSize: 10,
    fontFamily: F.mono,
    color: C.textDim,
    letterSpacing: 0.6,
    fontWeight: 600
  },
  queueList: { display: 'flex', flexDirection: 'column', gap: 6, overflow: 'auto' },

  qRow: {
    display: 'flex',
    gap: 12,
    padding: '10px 12px 10px 8px',
    background: C.bgRow,
    borderLeft: '3px solid',
    alignItems: 'flex-start'
  },
  qDot: { width: 6, height: 6, marginTop: 6, flex: '0 0 6px' },
  qKind: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    minWidth: 38,
    paddingTop: 2
  },
  qKindIcon: {
    fontSize: 18,
    color: C.magenta,
    textShadow: `0 0 4px ${C.magenta}66`,
    lineHeight: 1
  },
  qKindLabel: {
    fontSize: 9,
    color: C.textDim,
    fontFamily: F.mono,
    letterSpacing: 0.6,
    fontWeight: 700,
    marginTop: 2
  },
  qMain: { flex: 1, minWidth: 0 },
  qMeta: {
    display: 'flex',
    gap: 6,
    fontSize: 10.5,
    fontFamily: F.mono,
    color: C.textDim,
    letterSpacing: 0.3,
    alignItems: 'baseline'
  },
  qText: {
    fontSize: 12.5,
    color: C.text,
    marginTop: 4,
    lineHeight: 1.5,
    fontFamily: F.body
  },
  qSugg: { minWidth: 220, display: 'flex', flexDirection: 'column', gap: 4 },
  qSuggK: {
    fontSize: 9.5,
    color: C.textDim,
    fontFamily: F.mono,
    letterSpacing: 0.8,
    fontWeight: 600
  },
  qSuggChip: {
    padding: '3px 8px',
    border: '1px solid',
    fontSize: 10.5,
    fontFamily: F.mono,
    fontWeight: 700,
    letterSpacing: 0.4,
    display: 'inline-flex',
    gap: 6,
    alignItems: 'center',
    alignSelf: 'flex-start'
  },
  qSuggConf: { color: C.cyan, fontSize: 9.5 },
  select: {
    background: C.bgInput,
    border: `1px solid ${C.magenta}`,
    color: C.cyan,
    padding: '4px 8px',
    fontFamily: F.mono,
    fontSize: 10.5,
    outline: 'none'
  },
  qActions: { display: 'flex', flexDirection: 'column', gap: 4, minWidth: 100 },
  qBtnConfirm: {
    background: 'transparent',
    border: `1px solid ${C.cyan}`,
    color: C.cyan,
    padding: '4px 8px',
    fontFamily: F.mono,
    fontSize: 9.5,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer'
  },
  qBtnReject: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.textDim,
    padding: '4px 8px',
    fontFamily: F.mono,
    fontSize: 9.5,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer'
  },
  qBtnDel: {
    background: 'transparent',
    border: `1px solid ${C.line2}`,
    color: C.textMute,
    padding: '2px 8px',
    fontFamily: F.mono,
    fontSize: 11,
    cursor: 'pointer',
    alignSelf: 'flex-end'
  },

  footer: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    padding: 12,
    background: C.bgPanel,
    border: `1px solid ${C.line}`
  },
  warnLine: {
    display: 'flex',
    gap: 8,
    alignItems: 'center',
    fontSize: 11.5,
    color: C.textDim,
    fontFamily: F.mono,
    letterSpacing: 0.3
  },

  modalOverlay: {
    position: 'absolute',
    inset: 0,
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 50,
    backdropFilter: 'blur(2px)'
  },
  modal: {
    width: 1100,
    maxHeight: '92%',
    background: C.bg,
    border: `1px solid ${C.magenta}`,
    boxShadow: `0 0 40px ${C.magenta}66`,
    display: 'flex',
    flexDirection: 'column'
  },
  modalHdr: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    padding: 16,
    borderBottom: `1px solid ${C.line}`
  },
  modalBody: { flex: 1, overflow: 'auto', padding: 16 },
  modalFoot: {
    display: 'flex',
    gap: 10,
    alignItems: 'center',
    padding: 14,
    borderTop: `1px solid ${C.line}`,
    background: C.bgPanel
  },
  diffSubhdr: {
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 0.8,
    fontWeight: 700,
    fontFamily: F.mono,
    marginBottom: 10,
    textShadow: `0 0 4px ${C.magenta}66`
  },
  diffMarket: {
    marginBottom: 14,
    background: C.bgRow,
    border: `1px solid ${C.line}`
  },
  diffMarketHdr: {
    display: 'flex',
    alignItems: 'center',
    padding: '8px 12px',
    fontFamily: F.mono,
    fontSize: 12,
    fontWeight: 700,
    borderBottom: `1px solid ${C.line2}`
  },
  diffPre: {
    background: 'transparent',
    color: C.cyan,
    fontFamily: F.mono,
    fontSize: 11.5,
    padding: 12,
    margin: 0,
    whiteSpace: 'pre-wrap',
    lineHeight: 1.6
  },
  diffNoChange: {
    fontFamily: F.mono,
    fontSize: 11.5,
    color: C.textMute,
    padding: 10,
    background: C.bgRow,
    border: `1px solid ${C.line2}`
  }
}
