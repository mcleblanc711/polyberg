import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { usePmData } from '../../lib/pmDataContext'
import { colors as C, fonts as F } from '../../styles/tokens'
import type { Market, RuleRisk } from '../../lib/types'
import { AddMarketModal } from './AddMarketModal'
import { EditMarketModal } from './EditMarketModal'

const riskColor = (risk: RuleRisk): string =>
  risk === 'high' ? C.red : risk === 'medium' ? C.amber : C.textDim

const riskBorder = (risk: RuleRisk): string =>
  risk === 'high' ? C.red : risk === 'medium' ? C.amber : C.line

export const MarketsScreen = ({
  highlightId = null,
  onClearHighlight
}: {
  highlightId?: string | null
  onClearHighlight?: () => void
}) => {
  const pmData = usePmData()
  const [showAdd, setShowAdd] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [showExpired, setShowExpired] = useState(false)
  const [flashId, setFlashId] = useState<string | null>(null)
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})

  const active = pmData.markets.filter((m) => !m.expired)
  const expired = pmData.markets.filter((m) => m.expired)

  // ⌘K jump target: reveal the section it lives in, scroll to it, flash it.
  useEffect(() => {
    if (!highlightId) return
    if (expired.some((m) => m.id === highlightId)) setShowExpired(true)
    const t = setTimeout(() => {
      rowRefs.current[highlightId]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
      setFlashId(highlightId)
    }, 50)
    const clear = setTimeout(() => {
      setFlashId(null)
      onClearHighlight?.()
    }, 2600)
    return () => {
      clearTimeout(t)
      clearTimeout(clear)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightId])

  const renderRow = (m: Market, dimmed: boolean): JSX.Element => (
    <tr
      key={m.id}
      ref={(el) => {
        rowRefs.current[m.id] = el
      }}
      style={{
        opacity: dimmed ? 0.55 : 1,
        background: flashId === m.id ? C.magentaSft : 'transparent',
        transition: 'background 0.4s'
      }}
    >
      <td style={{ ...S.td, color: C.magenta, fontWeight: 700 }}>{m.id}</td>
      <td style={{ ...S.td, fontFamily: F.body, maxWidth: 320 }}>{m.name}</td>
      <td style={S.td}>{m.ruleKey}</td>
      <td style={S.td}>{m.oracle}</td>
      <td style={{ ...S.td, color: m.expired ? C.red : C.cyan }}>
        {m.resolutionDate.split('T')[0]}
        {m.expired ? ' ·  past' : ''}
      </td>
      <td style={S.td}>
        <span
          style={{
            ...S.chip,
            color: riskColor(m.ruleRisk),
            borderColor: riskBorder(m.ruleRisk)
          }}
        >
          {m.ruleRisk}
        </span>
      </td>
      <td style={{ ...S.td, color: C.cyan }}>
        {m.bookStatus === 'ok' ? (
          <>
            {(m.mark * 100).toFixed(1)}¢ <span style={{ color: C.textMute }}>{m.preferredSide}</span>
          </>
        ) : (
          '—'
        )}
      </td>
      <td style={{ ...S.td, whiteSpace: 'nowrap' }}>
        <button
          style={{ ...S.btnGhost, color: C.cyanText }}
          onClick={() => setEditId(m.id)}
        >
          EDIT
        </button>
        {m.url && (
          <button
            style={{ ...S.btnGhost, marginLeft: 4 }}
            title={`open ${m.url}`}
            onClick={() => void window.pm.openExternal(m.url)}
          >
            ↗
          </button>
        )}
      </td>
    </tr>
  )

  return (
    <div style={S.root}>
      {showAdd && <AddMarketModal onClose={() => setShowAdd(false)} />}
      {editId && <EditMarketModal marketId={editId} onClose={() => setEditId(null)} />}
      <div style={S.header}>
        <div>
          <div style={S.h1}>MARKET REGISTRY</div>
          <div style={S.h1Sub}>
            // market_registry.yaml · {active.length} active
            {expired.length > 0 ? ` · ${expired.length} expired` : ''} · read/write
          </div>
        </div>
        <button style={S.btnGhost} onClick={() => setShowAdd(true)}>
          + ADD MARKET
        </button>
      </div>
      <div style={S.panel}>
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>MARKET ID</th>
              <th style={S.th}>NAME</th>
              <th style={S.th}>RULE-KEY</th>
              <th style={S.th}>ORACLE</th>
              <th style={S.th}>RESOLVES</th>
              <th style={S.th}>RULE-RISK</th>
              <th style={S.th}>MARK · MID</th>
              <th style={S.th} />
            </tr>
          </thead>
          <tbody>
            {active.map((m) => renderRow(m, false))}
            {expired.length > 0 && (
              <tr>
                <td colSpan={8} style={S.expiredDivider}>
                  <button style={S.expiredToggle} onClick={() => setShowExpired((v) => !v)}>
                    {showExpired ? '▾' : '▸'} {expired.length} EXPIRED / RESOLVED — kept for history,
                    excluded from fetch-books
                  </button>
                </td>
              </tr>
            )}
            {showExpired && expired.map((m) => renderRow(m, true))}
          </tbody>
        </table>
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
    justifyContent: 'space-between'
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
  panel: {
    background: C.bgPanel,
    border: `1px solid ${C.line}`,
    padding: 14,
    overflow: 'auto',
    flex: 1
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 11.5,
    fontFamily: F.mono
  },
  th: {
    textAlign: 'left',
    padding: '8px 10px',
    color: C.textDim,
    fontSize: 9.5,
    letterSpacing: 1,
    fontWeight: 700,
    borderBottom: `1px solid ${C.line}`
  },
  td: {
    padding: '8px 10px',
    borderBottom: `1px solid ${C.line2}`,
    color: C.cyan
  },
  expiredDivider: {
    padding: '10px 10px 6px',
    borderBottom: `1px solid ${C.line2}`
  },
  expiredToggle: {
    background: 'transparent',
    border: 'none',
    color: C.textMute,
    fontFamily: F.mono,
    fontSize: 10,
    letterSpacing: 0.8,
    cursor: 'pointer',
    padding: 0,
    outline: 'none'
  },
  chip: {
    padding: '2px 7px',
    border: '1px solid',
    fontSize: 9.5,
    fontFamily: F.mono,
    fontWeight: 700,
    letterSpacing: 0.4,
    textTransform: 'uppercase'
  },
  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '4px 10px',
    fontFamily: F.mono,
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none'
  }
}
