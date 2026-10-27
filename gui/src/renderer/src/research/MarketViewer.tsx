import { useEffect, useRef, useState } from 'react'
import { SPANS, type ResearchActivity, type ResearchBook, type ResearchEventContext, type ResearchMarket, type ResearchOutcomeBook, type ResearchPriceHistory, type ResearchSpan } from '../../../shared/research'
import { SourceLink, px, shares, signedPx, usd, when } from './common'
import { PriceHistoryChart, SERIES_COLORS } from './PriceHistoryChart'

// Viewer panels read public data directly through the bridge. They bypass the provider's
// global loading state; cache hits write nothing, so the database watcher cannot loop.
export function PriceHistoryPanel({market}: {market: ResearchMarket}): JSX.Element {
  const id = market.identification.market_id
  const [span, setSpan] = useState<ResearchSpan>('1w')
  const [fit, setFit] = useState(false)
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(market.identification.outcomes.slice(1).map(o => o.outcome_id)))
  const [history, setHistory] = useState<ResearchPriceHistory | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [nonce, setNonce] = useState(0)
  const force = useRef(false)  // One-shot: only the Refetch click bypasses the cache TTL.
  useEffect(() => {
    let alive = true
    const refetch = force.current
    force.current = false
    setBusy(true); setError('')
    window.research.request<ResearchPriceHistory>({operation: 'price_history', market: id, span, ...(refetch ? {refetch: true} : {})})
      .then(result => { if (alive) setHistory(result) })
      .catch(e => { if (alive) setError(String(e)) })
      .finally(() => { if (alive) setBusy(false) })
    return () => { alive = false }
  }, [id, span, nonce])
  const series = history?.span === span ? history.series : []
  const lines = series.map((s, i) => ({series: s, color: SERIES_COLORS[i % SERIES_COLORS.length]})).filter(l => !hidden.has(l.series.outcome_id))
  const toggle = (oid: string): void => setHidden(prev => { const next = new Set(prev); if (next.has(oid)) next.delete(oid); else next.add(oid); return next })
  const latest = series.find(s => s.retrieved_at)
  return <section className="research-card research-history">
    <div className="research-row"><h3>Price history</h3>
      <div className="research-row research-segmented">{SPANS.map(s => <button key={s} className={span === s ? 'selected' : ''} onClick={() => setSpan(s)}>{s.toUpperCase()}</button>)}</div>
      <button className={fit ? 'selected' : ''} aria-pressed={fit} onClick={() => setFit(!fit)}>Fit range</button>
      <button disabled={busy} onClick={() => { force.current = true; setNonce(n => n + 1) }}>Refetch</button>
      {busy && <small role="status">Loading history…</small>}
    </div>
    <div className="research-row">{series.map((s, i) => <label key={s.outcome_id} className="research-toggle" style={{color: SERIES_COLORS[i % SERIES_COLORS.length]}}>
      <input type="checkbox" checked={!hidden.has(s.outcome_id)} onChange={() => toggle(s.outcome_id)} />{s.label}{s.points.length ? ` · ${px(s.points[s.points.length - 1].p)}` : ''}</label>)}</div>
    {error ? <p className="warning">{error}</p> : <PriceHistoryChart lines={lines} span={span} fit={fit} />}
    {series.flatMap(s => s.warnings.map(w => <p className="warning" key={`${s.outcome_id}:${w}`}>{s.label}: {w}</p>))}
    {latest && <><small>Retrieved {when(latest.retrieved_at)}</small>{latest.source_url && <SourceLink url={latest.source_url}>Public history source</SourceLink>}</>}
  </section>
}

export function ActivityCard({activity}: {activity: ResearchActivity | undefined}): JSX.Element {
  if (!activity) return <div className="research-card"><h3>Market activity</h3><p className="muted">No activity recorded yet. Refresh public data to collect it.</p></div>
  const rows: [string, string][] = [
    ['24h volume', usd(activity.volume_24h)], ['1w volume', usd(activity.volume_1w)], ['Total volume', usd(activity.volume_total)],
    ['Liquidity', usd(activity.liquidity)], ['Open interest', usd(activity.open_interest)],
    ['24h change', signedPx(activity.price_change_1d)], ['1w change', signedPx(activity.price_change_1w)], ['Spread', px(activity.spread)]
  ]
  return <div className="research-card"><h3>Market activity</h3>
    <div className="research-stats">{rows.map(([k, v]) => <div key={k}><span>{k}</span><strong>{v}</strong></div>)}</div>
    <small>Gamma figures retrieved {when(activity.retrieved_at)} · Open interest retrieved {when(activity.open_interest_retrieved_at)}. Changes describe the first outcome.</small>
    {activity.warnings.map(w => <p className="warning" key={w}>{w}</p>)}
  </div>
}

export function EventContextCard({event}: {event: ResearchEventContext | undefined}): JSX.Element | null {
  if (!event) return null
  return <div className="research-card"><h3>Event context</h3><strong>{event.title}</strong>
    {event.description ? <details><summary>Event description (not contract rules)</summary><pre className="verbatim">{event.description}</pre></details> : <p className="muted">No public event description.</p>}
    {event.page_url && <SourceLink url={event.page_url}>Open event page ↗</SourceLink>}
  </div>
}

function Ladder({book}: {book: ResearchOutcomeBook}): JSX.Element {
  const deepest = Math.max(book.bids[book.bids.length - 1]?.cumulative || 0, book.asks[book.asks.length - 1]?.cumulative || 0, 1)
  const side = (name: 'bids' | 'asks'): JSX.Element => <table className={`research-ladder ${name}`}><thead><tr><th>{name === 'bids' ? 'Bid' : 'Ask'}</th><th>Size</th><th>Cumulative</th></tr></thead>
    <tbody>{book[name].map(l => <tr key={l.price}><td>{px(l.price)}</td><td>{shares(l.size)}</td><td className="depth"><span style={{width: `${(l.cumulative / deepest) * 100}%`}} />{shares(l.cumulative)}</td></tr>)}
      {book[name].length === 0 && <tr><td colSpan={3} className="muted">No levels</td></tr>}</tbody></table>
  return <article className="research-card"><div className="research-row"><h3>{book.label}</h3>
    <small>Best bid {px(book.best_bid)} · Best ask {px(book.best_ask)} · Spread {px(book.spread)} · Book mid {px(book.book_midpoint)}</small></div>
    <div className="research-ladders">{side('bids')}{side('asks')}</div>
    <small>Showing {book.bids.length}/{book.bid_levels} bid and {book.asks.length}/{book.ask_levels} ask levels · Tick {book.tick_size ?? '—'} · Min size {book.min_order_size ?? '—'} · Retrieved {when(book.retrieved_at)}</small>
    {book.warnings.map(w => <p className="warning" key={w}>{w}</p>)}
  </article>
}

export function BookPanel({market}: {market: ResearchMarket}): JSX.Element {
  const id = market.identification.market_id
  const [book, setBook] = useState<ResearchBook | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let alive = true
    setBusy(true); setError('')
    window.research.request<ResearchBook>({operation: 'book', market: id})
      .then(result => { if (alive) setBook(result) })
      .catch(e => { if (alive) setError(String(e)) })
      .finally(() => { if (alive) setBusy(false) })
    return () => { alive = false }
  }, [id, reload])
  return <section className="research-stack"><div className="research-row"><h2>Order book depth</h2>
    <button disabled={busy} onClick={() => setReload(n => n + 1)}>{busy ? 'Loading…' : 'Reload book'}</button></div>
    <p className="muted">Read-only public depth (top 10 levels per side), fetched only when this tab is opened or reloaded. Orders are placed manually on Polymarket.</p>
    {error && <p className="warning">{error}</p>}
    {book?.market_id === id && book.outcomes.map(o => <Ladder key={o.outcome_id} book={o} />)}
  </section>
}
