import { useState, type CSSProperties } from 'react'
import { CatalystForm } from '../../components/CatalystForm'
import { fmtPct, fmtUsd } from '../../lib/format'
import { usePmData } from '../../lib/pmDataContext'
import type { Market, Position } from '../../lib/types'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'
import { PriceChart, Spark } from './charts'

type ExpandedTab = 'rules' | 'catalysts' | 'snapshot' | 'orders' | 'draft'

export const PositionCard = ({
  p,
  expanded,
  onToggle
}: {
  p: Position
  expanded: boolean
  onToggle: () => void
}) => {
  const pmData = usePmData()
  const m = pmData.marketById(p.marketId)
  if (!m) return null
  const pnl = (p.mark - p.avg) * p.shares
  const pnlPct = p.avg > 0 ? ((p.mark - p.avg) / p.avg) * 100 : 0
  const totPos = pnl >= 0
  const orders = pmData.openOrders.filter((o) => o.marketId === m.id)
  const accent = totPos ? C.cyan : C.red
  const ruleRiskColor =
    m.ruleRisk === 'high' ? C.red : m.ruleRisk === 'medium' ? C.amber : C.textDim
  const ruleRiskBorder =
    m.ruleRisk === 'high' ? C.red : m.ruleRisk === 'medium' ? C.amber : C.line
  return (
    <div
      style={{
        ...S.posCard,
        borderColor: expanded ? C.magenta : C.line,
        boxShadow: expanded ? `0 0 0 1px ${C.magenta}, 0 0 20px rgba(255,61,240,0.18)` : 'none'
      }}
    >
      <div style={S.posHead} onClick={onToggle}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={S.posTags}>
            <span
              style={{
                ...S.tag,
                background: p.side === 'YES' ? C.cyanSft : C.redSft,
                color: p.side === 'YES' ? C.cyan : C.red,
                border: `1px solid ${p.side === 'YES' ? C.cyan : C.red}`
              }}
            >
              {p.side}
            </span>
            <span style={{ ...S.tag, ...S.tagOutline, color: C.magenta, borderColor: C.magenta }}>
              {m.category.toUpperCase()}
            </span>
            <span style={{ ...S.tag, ...S.tagOutline, color: C.textDim, borderColor: C.line }}>
              {m.id}
            </span>
            {orders.length > 0 ? (
              <span style={{ ...S.tag, ...S.tagOutline, color: C.cyan, borderColor: C.cyan }}>
                {orders.length} OPEN ORD
              </span>
            ) : null}
            <span
              style={{
                ...S.tag,
                ...S.tagOutline,
                color: ruleRiskColor,
                borderColor: ruleRiskBorder
              }}
            >
              RULE-RISK · {m.ruleRisk.toUpperCase()}
            </span>
          </div>
          <div style={S.posTitle}>{m.name}</div>
          <div style={S.posSub}>
            resolves {m.resolutionDate.split('T')[0]} · {m.oracle}
          </div>
        </div>

        <div style={S.posStatGroup}>
          <div style={S.statBlock}>
            <div style={S.statK}>POSITION</div>
            <div style={S.statV}>{p.shares.toLocaleString()}</div>
            <div style={S.statSub}>
              {(p.avg * 100).toFixed(0)}¢ → {(p.mark * 100).toFixed(0)}¢
            </div>
          </div>
          <div style={S.statBlock}>
            <div style={S.statK}>NOTIONAL</div>
            <div style={S.statV}>{fmtUsd(p.shares * p.mark)}</div>
            <div style={S.statSub}>
              {pmData.equity > 0
                ? `${(((p.shares * p.mark) / pmData.equity) * 100).toFixed(0)}% equity`
                : '—'}
            </div>
          </div>
          <div style={S.statBlock}>
            <div style={S.statK}>OPEN P/L</div>
            <div style={{ ...S.statV, color: accent, textShadow: `0 0 10px ${accent}66` }}>
              {fmtUsd(pnl, true)}
            </div>
            <div style={{ ...S.statSub, color: accent, opacity: 0.85 }}>{fmtPct(pnlPct, true)}</div>
          </div>
          <div style={{ ...S.statBlock, alignItems: 'flex-end' }}>
            <div style={S.statK}>TREND · 13d</div>
            <Spark data={m.hist} w={120} h={30} color={accent} />
          </div>
          <div style={{ ...S.chev, transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>▾</div>
        </div>
      </div>
      {expanded ? <ExpandedBody m={m} p={p} /> : null}
    </div>
  )
}

const ExpandedBody = ({ m, p }: { m: Market; p: Position }) => {
  const pmData = usePmData()
  const [tab, setTab] = useState<ExpandedTab>('rules')
  const orders = pmData.openOrders.filter((o) => o.marketId === m.id)
  const tabs: [ExpandedTab, string][] = [
    ['rules', 'RESOLUTION RULE'],
    ['catalysts', 'CATALYSTS'],
    ['snapshot', 'SNAPSHOT'],
    ['orders', `OPEN ORDERS · ${orders.length}`],
    ['draft', 'DRAFT ORDER']
  ]
  return (
    <div style={S.expanded}>
      <div style={S.expGrid}>
        <div style={S.expPanel}>
          <div style={S.expPanelHdr}>
            <span>// price · 13d</span>
            <span
              style={{
                color: C.magenta,
                fontFamily: F.mono,
                fontSize: 12,
                textShadow: `0 0 6px ${C.magenta}88`
              }}
            >
              {(m.mark * 100).toFixed(1)}¢ · LIVE
            </span>
          </div>
          <PriceChart data={m.hist} w={500} h={170} />
          <div style={S.miniGrid}>
            <Mini k="BID" v={(m.bid * 100).toFixed(1) + '¢'} accent={C.cyan} />
            <Mini k="ASK" v={(m.ask * 100).toFixed(1) + '¢'} accent={C.red} />
            <Mini k="SPREAD" v={m.spread + '¢'} />
            <Mini k="LIQ" v={fmtUsd(m.liq)} />
            <Mini k="SNAP" v={m.snapshotAge + 'm old'} />
          </div>
        </div>

        <div style={S.expPanel}>
          <div style={S.tabRow}>
            {tabs.map(([id, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                style={{ ...S.expTab, ...(tab === id ? S.expTabActive : null) }}
              >
                {label}
              </button>
            ))}
          </div>
          <div style={S.tabBody}>
            {tab === 'rules' && <RulesPane m={m} />}
            {tab === 'catalysts' && <CatalystsPane m={m} />}
            {tab === 'snapshot' && <SnapshotPane m={m} />}
            {tab === 'orders' && <OrdersPane m={m} />}
            {tab === 'draft' && <DraftPane m={m} p={p} />}
          </div>
        </div>
      </div>
    </div>
  )
}

const Mini = ({ k, v, accent }: { k: string; v: string; accent?: string }) => (
  <div style={S.mini}>
    <div style={S.miniK}>{k}</div>
    <div style={{ ...S.miniV, color: accent || C.text }}>{v}</div>
  </div>
)

const RulesPane = ({ m }: { m: Market }) => (
  <div>
    <p style={S.ruleText}>{m.ruleText}</p>
    <div style={S.subhdr}>// rule-risk notes</div>
    {m.ruleRiskNotes.map((n, i) => (
      <div key={i} style={S.callout}>
        <div style={S.calloutText}>{n}</div>
      </div>
    ))}
  </div>
)

const CatalystsPane = ({ m }: { m: Market }) => {
  const [adding, setAdding] = useState(false)
  return (
  <div>
    <div style={S.subhdr}>// recent_catalysts.md · last 72h</div>
    {adding ? <CatalystForm marketId={m.id} onCancel={() => setAdding(false)} /> : null}
    <div style={{ position: 'relative', paddingLeft: 16, marginLeft: 4 }}>
      <div
        style={{
          position: 'absolute',
          left: 4,
          top: 8,
          bottom: 8,
          width: 1,
          background: C.line
        }}
      />
      {m.catalysts.map((c, i) => (
        <div key={i} style={S.tlRow}>
          <div style={S.tlDot} />
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ color: C.magenta, fontFamily: F.mono, fontSize: 11, letterSpacing: 0.3 }}>
                {c.t}
              </span>
              <span
                style={{
                  ...S.tag,
                  ...S.tagOutline,
                  color: C.cyan,
                  borderColor: C.cyan,
                  fontSize: 9.5
                }}
              >
                {c.src}
              </span>
            </div>
            <div style={S.tlText}>{c.txt}</div>
          </div>
        </div>
      ))}
    </div>
    {!adding && (
      <button style={{ ...S.btnGhost, marginTop: 10 }} onClick={() => setAdding(true)}>
        + ADD CATALYST
      </button>
    )}
  </div>
  )
}

const SnapshotPane = ({ m }: { m: Market }) => {
  const lastBefore = m.hist[m.hist.length - 3]!
  const delta = (m.mark - lastBefore) * 100
  return (
    <div>
      <div style={S.subhdr}>// snapshots/2026-05-08T13-24Z.json</div>
      <div style={S.snapGrid}>
        <SnapKV k="MARK" v={m.mark.toFixed(3)} />
        <SnapKV k="BID / ASK" v={`${m.bid.toFixed(3)} / ${m.ask.toFixed(3)}`} />
        <SnapKV k="SPREAD" v={m.spread + ' ¢'} />
        <SnapKV k="LIQUIDITY" v={fmtUsd(m.liq)} />
        <SnapKV k="SNAP AGE" v={m.snapshotAge + ' min'} />
        <SnapKV k="ORACLE" v={m.oracle} />
      </div>
      <div style={S.subhdr}>// diff vs previous</div>
      <div style={S.diffBlock}>
        <div style={S.diffLine}>
          <span style={S.diffPlus}>+</span>
          <span>
            mark · {lastBefore.toFixed(3)} → {m.mark.toFixed(3)}{' '}
            <span style={{ color: C.cyan }}>(+{delta.toFixed(1)}¢)</span>
          </span>
        </div>
        <div style={S.diffLine}>
          <span style={S.diffEq}>=</span>
          <span>
            spread · {m.spread} ¢ <span style={{ color: C.textMute }}>no change</span>
          </span>
        </div>
        <div style={S.diffLine}>
          <span style={S.diffPlus}>+</span>
          <span>
            liquidity · <span style={{ color: C.cyan }}>+$2,140</span>
          </span>
        </div>
        <div style={S.diffLine}>
          <span style={S.diffEq}>=</span>
          <span>
            missing-info · <span style={{ color: C.cyan }}>clean</span>
          </span>
        </div>
      </div>
    </div>
  )
}

const SnapKV = ({ k, v }: { k: string; v: string }) => (
  <div style={S.snapCell}>
    <div style={S.miniK}>{k}</div>
    <div style={{ ...S.miniV, fontSize: 14 }}>{v}</div>
  </div>
)

const OrdersPane = ({ m }: { m: Market }) => {
  const pmData = usePmData()
  const orders = pmData.openOrders.filter((o) => o.marketId === m.id)
  return (
    <div>
      <div style={S.subhdr}>
        // open_orders.yaml · {orders.length} working · LIMIT only
      </div>
      {orders.map((o) => (
        <div key={o.id} style={S.ordCard}>
          <div
            style={{
              ...S.tag,
              background: o.kind === 'BUY' ? C.cyanSft : C.redSft,
              color: o.kind === 'BUY' ? C.cyan : C.red,
              border: `1px solid ${o.kind === 'BUY' ? C.cyan : C.red}`
            }}
          >
            {o.kind}
          </div>
          <div style={{ flex: 1 }}>
            <div style={S.ordTitle}>
              {o.kind === 'BUY' ? 'Buy' : 'Sell'} {o.qty} {o.side} @ {(o.px * 100).toFixed(1)}¢
            </div>
            <div style={S.ordSub}>
              id <span style={{ color: C.magenta }}>{o.id}</span> · placed{' '}
              {o.placed.replace('T', ' ').slice(0, 16)}Z · {fmtUsd(o.px * o.qty)} notional
            </div>
          </div>
          <div style={S.ordStatus}>● {o.status}</div>
        </div>
      ))}
    </div>
  )
}

type DraftSide = 'YES' | 'NO'
type DraftKind = 'BUY' | 'SELL'

interface DraftState {
  side: DraftSide
  kind: DraftKind
  price: string
  shares: string
  notes: string
}

const draftDefaults = (m: Market): DraftState => ({
  side: m.preferredSide,
  kind: 'BUY',
  price: (m.mark > 0 ? m.mark : 0.5).toFixed(2),
  shares: '100',
  notes: ''
})

const DraftPane = ({ m }: { m: Market; p: Position }) => {
  const [draft, setDraft] = useState<DraftState>(draftDefaults(m))
  const [status, setStatus] = useState<'idle' | 'writing' | 'ok' | 'err'>('idle')
  const [errMsg, setErrMsg] = useState<string | null>(null)

  const priceNum = Number(draft.price)
  const sharesNum = Number(draft.shares)
  const notional = Number.isFinite(priceNum) && Number.isFinite(sharesNum) ? priceNum * sharesNum : 0
  const valid =
    Number.isFinite(priceNum) &&
    priceNum > 0 &&
    priceNum < 1 &&
    Number.isFinite(sharesNum) &&
    sharesNum > 0

  const reset = (): void => {
    setDraft(draftDefaults(m))
    setStatus('idle')
    setErrMsg(null)
  }

  const write = async (): Promise<void> => {
    if (!valid) return
    setStatus('writing')
    setErrMsg(null)
    try {
      await window.pm.writeDraftOrder({
        marketId: m.id,
        side: draft.side,
        kind: draft.kind,
        price: priceNum,
        shares: sharesNum,
        notes: draft.notes || undefined
      })
      setStatus('ok')
    } catch (e) {
      setStatus('err')
      setErrMsg(String(e))
    }
  }

  const sideAccent = draft.side === 'YES' ? C.cyan : C.red
  const yamlPreview = `${draft.kind === 'BUY' ? 'buy_orders' : 'sell_orders'}:
  - market_id: ${m.id}
    side: "${draft.side}"
    price: ${Number.isFinite(priceNum) ? priceNum : 0}
    shares: ${Number.isFinite(sharesNum) ? sharesNum : 0}
    order_type: limit${draft.notes ? `\n    notes: ${JSON.stringify(draft.notes)}` : ''}`

  return (
    <div>
      <div style={S.subhdr}>// draft → open_orders.yaml · no execution</div>
      <div style={S.draftGrid}>
        <DfField k="MARKET" v={m.id} accent={C.magenta} />
        <DfToggle
          k="SIDE"
          options={['YES', 'NO']}
          value={draft.side}
          onChange={(v) => setDraft({ ...draft, side: v as DraftSide })}
          accent={sideAccent}
        />
        <DfToggle
          k="KIND"
          options={['BUY', 'SELL']}
          value={draft.kind}
          onChange={(v) => setDraft({ ...draft, kind: v as DraftKind })}
        />
        <DfInput
          k="PRICE (0–1)"
          value={draft.price}
          onChange={(v) => setDraft({ ...draft, price: v })}
          inputMode="decimal"
        />
        <DfInput
          k="SHARES"
          value={draft.shares}
          onChange={(v) => setDraft({ ...draft, shares: v })}
          inputMode="numeric"
        />
        <DfField k="NOTIONAL" v={fmtUsd(notional)} />
      </div>
      <div style={{ marginTop: 8 }}>
        <div style={S.dfK}>NOTES</div>
        <input
          type="text"
          value={draft.notes}
          onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
          placeholder="optional · why this order"
          style={S.draftNotes}
        />
      </div>
      <div style={S.subhdr}>// yaml preview</div>
      <pre style={S.codeBlock}>{yamlPreview}</pre>
      <div style={{ display: 'flex', gap: 10, marginTop: 12, alignItems: 'center' }}>
        <button
          style={{
            ...S.btnPrimaryNarrow,
            opacity: valid && status !== 'writing' ? 1 : 0.5,
            cursor: valid && status !== 'writing' ? 'pointer' : 'not-allowed'
          }}
          onClick={write}
          disabled={!valid || status === 'writing'}
        >
          {status === 'writing' ? 'WRITING…' : 'WRITE TO open_orders.yaml ▸'}
        </button>
        <button style={S.btnGhost} onClick={reset}>
          DISCARD
        </button>
        <span style={{ flex: 1 }} />
        {status === 'ok' && (
          <span
            style={{
              fontSize: 10.5,
              color: C.cyan,
              fontFamily: F.mono,
              letterSpacing: 0.5,
              textShadow: `0 0 6px ${C.cyan}66`
            }}
          >
            ● APPENDED · MANUAL EXEC STILL REQUIRED
          </span>
        )}
        {status === 'err' && (
          <span style={{ fontSize: 10.5, color: C.red, fontFamily: F.mono, letterSpacing: 0.4 }}>
            ✕ {errMsg}
          </span>
        )}
        {status === 'idle' && (
          <span
            style={{
              fontSize: 10.5,
              color: C.amber,
              fontFamily: F.mono,
              letterSpacing: 0.5,
              textShadow: `0 0 6px ${C.amber}66`
            }}
          >
            ● NO ORDER PLACED · MANUAL EXEC
          </span>
        )}
      </div>
    </div>
  )
}

const DfField = ({ k, v, accent }: { k: string; v: string; accent?: string }) => (
  <div style={S.dfField}>
    <div style={S.dfK}>{k}</div>
    <div style={{ ...S.dfV, color: accent || C.text }}>{v}</div>
  </div>
)

const DfInput = ({
  k,
  value,
  onChange,
  inputMode
}: {
  k: string
  value: string
  onChange: (v: string) => void
  inputMode?: 'decimal' | 'numeric'
}) => (
  <div style={S.dfField}>
    <div style={S.dfK}>{k}</div>
    <input
      type="text"
      inputMode={inputMode}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={S.draftInput}
    />
  </div>
)

const DfToggle = ({
  k,
  options,
  value,
  onChange,
  accent
}: {
  k: string
  options: [string, string]
  value: string
  onChange: (v: string) => void
  accent?: string
}) => (
  <div style={S.dfField}>
    <div style={S.dfK}>{k}</div>
    <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
      {options.map((opt) => {
        const on = opt === value
        return (
          <button
            key={opt}
            onClick={() => onChange(opt)}
            style={{
              ...S.draftToggle,
              borderColor: on ? accent || C.magenta : C.line,
              color: on ? accent || C.magenta : C.textDim,
              background: on ? `${accent || C.magenta}22` : 'transparent',
              fontWeight: on ? 700 : 500
            }}
          >
            {opt}
          </button>
        )
      })}
    </div>
  </div>
)

const S: Record<string, CSSProperties> = {
  posCard: {
    background: C.bgPanel,
    border: '1px solid',
    clipPath: clipCard,
    transition: 'all 0.15s'
  },
  posHead: { padding: '14px 16px', cursor: 'pointer' },
  posTags: { display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' },
  tag: {
    padding: '2px 8px',
    fontSize: 9.5,
    fontWeight: 700,
    letterSpacing: 0.8,
    fontFamily: F.mono,
    textTransform: 'uppercase'
  },
  tagOutline: { background: 'transparent', border: '1px solid' },
  posTitle: {
    fontSize: 16,
    fontWeight: 600,
    lineHeight: 1.35,
    fontFamily: F.display,
    color: C.text,
    letterSpacing: -0.1
  },
  posSub: { fontSize: 11, color: C.textDim, marginTop: 3, fontFamily: F.mono, letterSpacing: 0.3 },
  posStatGroup: { display: 'flex', gap: 26, alignItems: 'center', marginTop: 12 },
  statBlock: { display: 'flex', flexDirection: 'column', gap: 2 },
  statK: { fontSize: 9.5, color: C.textDim, letterSpacing: 1, fontWeight: 600, fontFamily: F.mono },
  statV: { fontSize: 17, fontFamily: F.mono, fontWeight: 700, letterSpacing: -0.3, lineHeight: 1.2 },
  statSub: { fontSize: 10.5, color: C.textMute, fontFamily: F.mono, letterSpacing: 0.3 },
  chev: {
    color: C.magenta,
    fontSize: 16,
    transition: 'transform 0.2s',
    marginLeft: 4,
    textShadow: `0 0 6px ${C.magenta}`
  },

  expanded: { borderTop: `1px solid ${C.line}`, padding: 14, background: C.bgRow },
  expGrid: { display: 'grid', gridTemplateColumns: '540px 1fr', gap: 12 },
  expPanel: { background: C.bgPanel, border: `1px solid ${C.line}`, padding: 14 },
  expPanelHdr: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: 10.5,
    color: C.textDim,
    letterSpacing: 0.6,
    marginBottom: 10,
    fontWeight: 600,
    fontFamily: F.mono
  },

  miniGrid: {
    display: 'flex',
    gap: 0,
    marginTop: 14,
    paddingTop: 12,
    borderTop: `1px solid ${C.line2}`
  },
  mini: { flex: 1, paddingRight: 10, borderRight: `1px solid ${C.line2}` },
  miniK: { fontSize: 9.5, color: C.textDim, letterSpacing: 1, fontFamily: F.mono, fontWeight: 600 },
  miniV: { fontSize: 13, fontFamily: F.mono, marginTop: 3, fontWeight: 600 },

  tabRow: { display: 'flex', gap: 0, marginBottom: 12, borderBottom: `1px solid ${C.line}` },
  expTab: {
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    color: C.textDim,
    padding: '6px 10px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 600,
    cursor: 'pointer',
    letterSpacing: 0.6,
    outline: 'none'
  },
  expTabActive: {
    color: C.magenta,
    borderBottom: `2px solid ${C.magenta}`,
    textShadow: `0 0 6px ${C.magenta}66`
  },
  tabBody: { fontSize: 12.5, lineHeight: 1.55 },

  ruleText: {
    fontSize: 12.5,
    lineHeight: 1.65,
    color: C.text,
    margin: 0,
    padding: '8px 0',
    borderTop: `1px solid ${C.line2}`,
    borderBottom: `1px solid ${C.line2}`,
    fontFamily: F.body
  },
  subhdr: {
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 0.8,
    fontWeight: 600,
    margin: '12px 0 8px',
    fontFamily: F.mono,
    textShadow: `0 0 4px ${C.magenta}66`
  },

  callout: {
    display: 'flex',
    gap: 10,
    padding: '6px 12px',
    background: C.amberSft,
    marginBottom: 5,
    alignItems: 'flex-start',
    borderLeft: `2px solid ${C.amber}`
  },
  calloutText: { fontSize: 12, lineHeight: 1.45, flex: 1, color: C.text },

  tlRow: { display: 'flex', gap: 12, paddingBottom: 12, position: 'relative' },
  tlDot: {
    position: 'absolute',
    left: -16,
    top: 6,
    width: 9,
    height: 9,
    background: C.magenta,
    boxShadow: `0 0 0 3px ${C.magentaSft}, 0 0 0 4px ${C.bgPanel}, 0 0 8px ${C.magenta}`
  },
  tlText: { fontSize: 12.5, color: C.text, marginTop: 4, lineHeight: 1.5, fontFamily: F.body },

  snapGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 6,
    marginBottom: 6
  },
  snapCell: { background: C.bgRow, border: `1px solid ${C.line2}`, padding: '6px 10px' },
  diffBlock: {
    background: C.bgRow,
    border: `1px solid ${C.line2}`,
    padding: 12,
    fontFamily: F.mono,
    fontSize: 12
  },
  diffLine: { display: 'flex', gap: 10, padding: '3px 0' },
  diffPlus: { color: C.cyan, width: 14 },
  diffEq: { color: C.textMute, width: 14 },

  ordCard: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '10px 12px',
    background: C.bgRow,
    border: `1px solid ${C.line2}`,
    marginBottom: 5
  },
  ordTitle: { fontSize: 12.5, fontFamily: F.mono, color: C.text },
  ordSub: {
    fontSize: 10.5,
    color: C.textDim,
    fontFamily: F.mono,
    marginTop: 2,
    letterSpacing: 0.3
  },
  ordStatus: {
    fontSize: 10.5,
    color: C.amber,
    fontFamily: F.mono,
    letterSpacing: 0.6,
    textShadow: `0 0 6px ${C.amber}66`
  },

  draftGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 6,
    marginBottom: 4
  },
  dfField: { background: C.bgRow, border: `1px solid ${C.line2}`, padding: '8px 12px' },
  dfK: { fontSize: 9.5, color: C.textDim, letterSpacing: 1, fontFamily: F.mono, fontWeight: 600 },
  dfV: { fontSize: 14, fontFamily: F.mono, marginTop: 4, fontWeight: 700 },
  draftInput: {
    width: '100%',
    background: C.bg,
    border: `1px solid ${C.line}`,
    color: C.text,
    fontFamily: F.mono,
    fontSize: 13,
    padding: '5px 8px',
    marginTop: 4,
    outline: 'none',
    fontWeight: 700
  },
  draftNotes: {
    width: '100%',
    background: C.bg,
    border: `1px solid ${C.line}`,
    color: C.text,
    fontFamily: F.mono,
    fontSize: 12,
    padding: '6px 10px',
    marginTop: 4,
    outline: 'none'
  },
  draftToggle: {
    flex: 1,
    background: 'transparent',
    border: '1px solid',
    fontFamily: F.mono,
    fontSize: 11,
    letterSpacing: 0.6,
    padding: '4px 6px',
    cursor: 'pointer',
    outline: 'none'
  },
  codeBlock: {
    background: C.bg,
    border: `1px solid ${C.line2}`,
    padding: 12,
    fontSize: 11.5,
    color: C.cyan,
    fontFamily: F.mono,
    lineHeight: 1.6,
    margin: 0,
    whiteSpace: 'pre-wrap'
  },

  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '7px 12px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 600,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none'
  },
  btnPrimaryNarrow: {
    background: C.magenta,
    color: C.bg,
    border: 'none',
    padding: '8px 14px',
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
