import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { usePmData } from '../../lib/pmDataContext'
import { colors as C, fonts as F } from '../../styles/tokens'
import type { Market } from '../../lib/types'

// Shape of the JSON printed by `hedge --json` (see polyberg.hedge.group_to_dict).
interface HedgeScenario {
  key: string
  label: string
  feasible: boolean
  leg_payoffs: number[]
  net: number
  return_pct: number | null
}
interface HedgeGroupOut {
  group_id: string
  name: string
  exclusivity_verified: boolean
  has_held: boolean
  total_cost: number
  guaranteed_min: number | null
  locked_profit: boolean
  locked_loss: boolean
  worst: HedgeScenario | null
  best: HedgeScenario | null
  legs: { market_id: string; label: string; side: string; price: number; shares: number }[]
  scenarios: HedgeScenario[]
  notes: string[]
}

interface LegInput {
  include: boolean
  side: 'YES' | 'NO'
  price: string
  shares: string
  held: boolean
}

const bandLabel = (m: Market): string =>
  m.name.includes(' — ') ? m.name.split(' — ')[1].trim() : m.name

const familyName = (members: Market[]): string => {
  const withDash = members.find((m) => m.name.includes(' — '))
  if (withDash) return withDash.name.split(' — ')[0].trim()
  return members[0]?.name ?? members[0]?.eventSlug ?? '—'
}

const money = (v: number): string => (v < 0 ? `-$${Math.abs(v).toFixed(2)}` : `$${v.toFixed(2)}`)

export const HedgeScreen = () => {
  const pmData = usePmData()

  // Multi-market event families (the candidate mutually-exclusive sets). A family
  // is any event_slug shared by 2+ registry markets.
  const families = useMemo(() => {
    const byslug = new Map<string, Market[]>()
    for (const m of pmData.markets) {
      if (!m.eventSlug) continue
      const arr = byslugGet(byslug, m.eventSlug)
      arr.push(m)
    }
    const held = new Set(pmData.positions.map((p) => p.marketId))
    return [...byslug.entries()]
      .filter(([, members]) => members.length > 1)
      .map(([slug, members]) => ({
        slug,
        members,
        name: familyName(members),
        verified: members.some((m) => m.negRisk === true),
        unknownRisk: members.every((m) => m.negRisk === null),
        hasHeld: members.some((m) => held.has(m.id))
      }))
      .sort((a, b) => Number(b.hasHeld) - Number(a.hasHeld) || a.name.localeCompare(b.name))
  }, [pmData.markets, pmData.positions])

  const [slug, setSlug] = useState('')
  const [legs, setLegs] = useState<Record<string, LegInput>>({})
  const [result, setResult] = useState<HedgeGroupOut | null>(null)
  const [state, setState] = useState<'idle' | 'calculating' | 'error'>('idle')
  const [errMsg, setErrMsg] = useState('')

  const family = families.find((f) => f.slug === slug) ?? null

  // Build the leg editor whenever the selected family changes: held bands are
  // pre-included at their entry price/side, the rest seeded from the live mid.
  useEffect(() => {
    if (!family) {
      setLegs({})
      setResult(null)
      return
    }
    const next: Record<string, LegInput> = {}
    for (const m of family.members) {
      const pos = pmData.positions.find((p) => p.marketId === m.id)
      const seedPrice = pos
        ? pos.avg
        : m.bookStatus === 'ok' && m.mark > 0
          ? m.mark
          : 0.5
      next[m.id] = {
        include: !!pos,
        side: pos ? pos.side : m.preferredSide,
        price: seedPrice.toFixed(4),
        shares: pos ? String(Math.round(pos.shares)) : '0',
        held: !!pos
      }
    }
    setLegs(next)
    setResult(null)
  }, [slug]) // eslint-disable-line react-hooks/exhaustive-deps

  const update = (id: string, patch: Partial<LegInput>): void =>
    setLegs((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }))

  const includedSpecs = useMemo(() => {
    const specs: string[] = []
    for (const [id, leg] of Object.entries(legs)) {
      const shares = Number(leg.shares)
      const price = Number(leg.price)
      if (!leg.include || !(shares > 0) || !(price >= 0 && price <= 1)) continue
      specs.push(`${id}:${leg.side}:${price}:${shares}`)
    }
    return specs
  }, [legs])

  const calculate = async (): Promise<void> => {
    if (!family || includedSpecs.length === 0) return
    setState('calculating')
    const args = ['--no-holdings', '--event', family.slug, '--all-groups', '--json']
    for (const spec of includedSpecs) args.push('--leg', spec)
    const r = await window.pm.runStage('hedge', args)
    if (!r.ok) {
      setErrMsg(r.stderr.trim() || r.stdout.trim() || `exit ${r.code}`)
      setState('error')
      return
    }
    try {
      const data = JSON.parse(r.stdout) as { groups: HedgeGroupOut[] }
      setResult(data.groups[0] ?? null)
      setState('idle')
    } catch (err) {
      setErrMsg(String(err))
      setState('error')
    }
  }

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.h1}>HEDGE CALCULATOR</div>
          <div style={S.h1Sub}>
            // payoff across mutually-exclusive bands — exactly one resolves YES
          </div>
        </div>
        <select style={S.select} value={slug} onChange={(e) => setSlug(e.target.value)}>
          <option value="">choose a market family…</option>
          {families.map((f) => (
            <option key={f.slug} value={f.slug}>
              {f.hasHeld ? '◆ ' : ''}
              {f.name} ({f.members.length} bands{f.verified ? ', neg-risk' : ''})
            </option>
          ))}
        </select>
      </div>

      {!family && (
        <div style={S.empty}>
          {families.length === 0
            ? 'no multi-band families in the registry yet — add a neg-risk event from the MARKETS tab'
            : 'pick a family above to build a hedge. ◆ = you hold a band in it.'}
        </div>
      )}

      {family && (
        <div style={S.body}>
          <div style={S.panel}>
            <div style={S.panelHdr}>// legs — edit price / shares, toggle side, include</div>
            {!family.verified && (
              <div style={S.warn}>
                ⚠ {family.unknownRisk ? 'exclusivity not recorded' : 'not neg-risk'} — payoffs
                assume exactly one band resolves YES. Re-add this event from MARKETS to record
                neg-risk, or verify before trusting.
              </div>
            )}
            <table style={S.table}>
              <thead>
                <tr>
                  <th style={S.th} />
                  <th style={{ ...S.th, textAlign: 'left' }}>BAND</th>
                  <th style={S.th}>SIDE</th>
                  <th style={S.th}>PRICE</th>
                  <th style={S.th}>SHARES</th>
                </tr>
              </thead>
              <tbody>
                {family.members.map((m) => {
                  const leg = legs[m.id]
                  if (!leg) return null
                  return (
                    <tr key={m.id} style={{ opacity: leg.include ? 1 : 0.5 }}>
                      <td style={S.td}>
                        <input
                          type="checkbox"
                          checked={leg.include}
                          onChange={(e) => update(m.id, { include: e.target.checked })}
                          style={{ accentColor: C.magenta, cursor: 'pointer' }}
                        />
                      </td>
                      <td style={{ ...S.td, textAlign: 'left' }}>
                        {bandLabel(m)}
                        {leg.held && <span style={S.heldTag}>held</span>}
                      </td>
                      <td style={S.td}>
                        <div style={S.sideRow}>
                          {(['YES', 'NO'] as const).map((s) => (
                            <button
                              key={s}
                              style={{ ...S.sideBtn, ...(leg.side === s ? S.sideOn : null) }}
                              onClick={() => update(m.id, { side: s })}
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      </td>
                      <td style={S.td}>
                        <input
                          style={S.numInput}
                          value={leg.price}
                          onChange={(e) => update(m.id, { price: e.target.value })}
                        />
                      </td>
                      <td style={S.td}>
                        <input
                          style={S.numInput}
                          value={leg.shares}
                          onChange={(e) => update(m.id, { shares: e.target.value })}
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <button
              style={{ ...S.btnPrimary, opacity: includedSpecs.length ? 1 : 0.4 }}
              onClick={() => void calculate()}
              disabled={!includedSpecs.length || state === 'calculating'}
            >
              {state === 'calculating' ? 'CALCULATING…' : 'CALCULATE HEDGE ▸'}
            </button>
          </div>

          <div style={S.panel}>
            <div style={S.panelHdr}>// payoff by outcome</div>
            {state === 'error' && <pre style={S.errBox}>{errMsg.slice(0, 800)}</pre>}
            {!result && state !== 'error' && (
              <div style={S.empty}>
                set your legs and hit CALCULATE to see the payoff in every resolution scenario
              </div>
            )}
            {result && (
              <>
                <div style={S.summaryRow}>
                  <span style={S.summaryItem}>
                    capital at risk <b style={{ color: C.text }}>{money(result.total_cost)}</b>
                  </span>
                  {result.worst && (
                    <span style={S.summaryItem}>
                      worst{' '}
                      <b style={{ color: result.worst.net < 0 ? C.red : C.cyan }}>
                        {money(result.worst.net)}
                      </b>
                    </span>
                  )}
                  {result.best && (
                    <span style={S.summaryItem}>
                      best <b style={{ color: C.cyan }}>{money(result.best.net)}</b>
                    </span>
                  )}
                </div>
                {result.locked_profit && (
                  <div style={S.lockBanner}>
                    ✅ profit locked in — at least {money(result.guaranteed_min ?? 0)} whatever
                    resolves
                  </div>
                )}
                <table style={S.table}>
                  <thead>
                    <tr>
                      <th style={{ ...S.th, textAlign: 'left' }}>IF WINNER IS</th>
                      <th style={{ ...S.th, textAlign: 'right' }}>NET P&L</th>
                      <th style={{ ...S.th, textAlign: 'right' }}>RETURN</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.scenarios
                      .filter((s) => s.feasible)
                      .map((s) => {
                        const isWorst = result.worst?.key === s.key
                        const isBest = result.best?.key === s.key
                        return (
                          <tr key={s.key}>
                            <td style={{ ...S.td, textAlign: 'left', color: C.text }}>
                              {s.label}
                              {isWorst && <span style={{ ...S.tag, color: C.red }}>worst</span>}
                              {isBest && <span style={{ ...S.tag, color: C.cyan }}>best</span>}
                            </td>
                            <td
                              style={{
                                ...S.td,
                                textAlign: 'right',
                                color: s.net < 0 ? C.red : C.cyan
                              }}
                            >
                              {money(s.net)}
                            </td>
                            <td style={{ ...S.td, textAlign: 'right', color: C.textDim }}>
                              {s.return_pct === null ? '—' : `${s.return_pct >= 0 ? '+' : ''}${s.return_pct.toFixed(1)}%`}
                            </td>
                          </tr>
                        )
                      })}
                  </tbody>
                </table>
                {result.notes.map((n, i) => (
                  <div key={i} style={S.note}>
                    {n}
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Small Map helper so the families useMemo stays readable.
const byslugGet = (m: Map<string, Market[]>, slug: string): Market[] => {
  let arr = m.get(slug)
  if (!arr) {
    arr = []
    m.set(slug, arr)
  }
  return arr
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
  header: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 },
  h1: { fontSize: 18, fontWeight: 700, fontFamily: F.display, letterSpacing: 1, color: C.text },
  h1Sub: { fontSize: 11, color: C.textDim, fontFamily: F.mono, marginTop: 3, letterSpacing: 0.4 },
  select: {
    background: C.bg,
    color: C.text,
    border: `1px solid ${C.line2}`,
    padding: '7px 10px',
    fontFamily: F.mono,
    fontSize: 11,
    outline: 'none',
    maxWidth: 460
  },
  body: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, flex: 1, minHeight: 0 },
  panel: {
    background: C.bgPanel,
    border: `1px solid ${C.line}`,
    padding: 14,
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    minHeight: 0,
    overflow: 'auto'
  },
  panelHdr: {
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 0.8,
    fontWeight: 700,
    fontFamily: F.mono,
    textShadow: `0 0 4px ${C.magenta}66`
  },
  warn: {
    border: `1px solid ${C.amber}`,
    color: C.amber,
    background: `${C.amber}11`,
    padding: '7px 9px',
    fontFamily: F.mono,
    fontSize: 10.5,
    lineHeight: 1.45
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 11.5, fontFamily: F.mono },
  th: {
    textAlign: 'center',
    padding: '6px 8px',
    color: C.textDim,
    fontSize: 9,
    letterSpacing: 0.8,
    fontWeight: 700,
    borderBottom: `1px solid ${C.line}`
  },
  td: {
    padding: '6px 8px',
    borderBottom: `1px solid ${C.line2}`,
    color: C.cyan,
    textAlign: 'center'
  },
  heldTag: {
    marginLeft: 6,
    fontSize: 8,
    color: C.magenta,
    border: `1px solid ${C.magenta}66`,
    borderRadius: 2,
    padding: '0 4px',
    textTransform: 'uppercase'
  },
  tag: { marginLeft: 6, fontSize: 8.5, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase' },
  sideRow: { display: 'flex', justifyContent: 'center', gap: 0 },
  sideBtn: {
    background: 'transparent',
    border: `1px solid ${C.line2}`,
    color: C.textDim,
    padding: '3px 8px',
    fontFamily: F.mono,
    fontSize: 9.5,
    fontWeight: 700,
    cursor: 'pointer',
    outline: 'none'
  },
  sideOn: { color: C.cyan, borderColor: C.cyan, boxShadow: `inset 0 0 8px ${C.cyan}22` },
  numInput: {
    width: 64,
    background: C.bg,
    color: C.text,
    border: `1px solid ${C.line2}`,
    padding: '4px 6px',
    fontFamily: F.mono,
    fontSize: 11,
    textAlign: 'right',
    outline: 'none'
  },
  btnPrimary: {
    alignSelf: 'flex-start',
    marginTop: 6,
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
    cursor: 'pointer',
    outline: 'none'
  },
  summaryRow: { display: 'flex', gap: 16, flexWrap: 'wrap' },
  summaryItem: { fontFamily: F.mono, fontSize: 11, color: C.textDim },
  lockBanner: {
    border: `1px solid ${C.cyan}`,
    background: `${C.cyan}11`,
    color: C.cyan,
    padding: '7px 9px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.3
  },
  note: {
    color: C.textDim,
    fontFamily: F.mono,
    fontSize: 10,
    lineHeight: 1.45,
    borderLeft: `2px solid ${C.line}`,
    paddingLeft: 8
  },
  empty: {
    border: `1px dashed ${C.line}`,
    padding: 20,
    color: C.textMute,
    fontFamily: F.mono,
    fontSize: 11.5,
    textAlign: 'center'
  },
  errBox: {
    background: C.bg,
    border: `1px solid ${C.red}`,
    padding: 10,
    fontSize: 11,
    fontFamily: F.mono,
    color: C.red,
    margin: 0,
    whiteSpace: 'pre-wrap'
  }
}
