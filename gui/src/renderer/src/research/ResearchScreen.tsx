import { useEffect, useState, type FormEvent } from 'react'
import { ANNOTATIONS, CATEGORIES, RELATIONSHIPS, STATUSES, type ResearchDiscovery, type ResearchMarket, type ResearchPacketResult, type ResearchRules, type ResearchRulesChange, type ResearchRulesResult } from '../../../shared/research'
import { SourceLink, attempt, px, signedPx, when } from './common'
import { ActivityCard, BookPanel, EventContextCard, PriceHistoryPanel } from './MarketViewer'
import { useResearch } from './ResearchProvider'

function RulesChange({change}: {change: ResearchRulesChange}): JSX.Element {
  const fields = Object.entries(change.fields)
  return <div className="research-card"><h3>Changes from v{change.previous_version_id}</h3>
    {fields.map(([field, [before, after]]) => <p key={field}>{field}: <span className="muted">{before ?? 'unset'}</span> → <strong>{after ?? 'unset'}</strong></p>)}
    {change.text_diff.length ? <pre className="verbatim research-diff">{change.text_diff.map((line, i) => <span key={i} className={line.startsWith('+') && !line.startsWith('+++') ? 'added' : line.startsWith('-') && !line.startsWith('---') ? 'removed' : ''}>{line}{'\n'}</span>)}</pre>
      : <p className="muted">Rules text unchanged; only public metadata changed.</p>}
  </div>
}
function Prices({market}: {market: ResearchMarket}): JSX.Element {
  const quotes = new Map(market.snapshot?.quotes.map(q => [q.outcome_id, q]))
  return <div className="research-table-wrap"><table><thead><tr><th>Outcome</th><th>Displayed</th><th>Bid</th><th>Ask</th><th>Midpoint</th><th>Last trade</th></tr></thead>
    <tbody>{market.identification.outcomes.map(o => { const q = quotes.get(o.outcome_id); return <tr key={o.outcome_id}>
      <th title={`Outcome ${o.outcome_id} · Asset ${o.asset_id || 'unavailable'}`}>{o.label}</th>
      <td>{px(q?.displayed_price)}</td><td>{px(q?.best_bid)}</td><td>{px(q?.best_ask)}</td><td>{px(q?.midpoint)}</td><td>{px(q?.last_trade)}</td>
    </tr> })}</tbody></table></div>
}
function EntryForm({market}: {market: ResearchMarket}): JSX.Element {
  const {request, loading} = useResearch()
  const [category, setCategory] = useState<string>('observation')
  const [text, setText] = useState('')
  const [urls, setUrls] = useState('')
  const [published, setPublished] = useState('')
  const [observed, setObserved] = useState('')
  const submit = (e: FormEvent): void => {
    e.preventDefault()
    attempt(async () => {
      await request({operation: 'note', market: market.identification.market_id, category, text,
        sources: urls.split('\n').map(s => s.trim()).filter(Boolean).map(url => ({url, published_at: published || null, observed_at: observed || null}))})
      setText(''); setUrls('')
    })
  }
  return <form className="research-form" onSubmit={submit}>
    <label>Entry category<select value={category} onChange={e => setCategory(e.target.value)}>{CATEGORIES.map(c => <option key={c}>{c}</option>)}</select></label>
    <label>Research entry<textarea required value={text} onChange={e => setText(e.target.value)} placeholder="Record evidence, a question, or an interpretation…" /></label>
    <label>Source URLs · one per line<textarea value={urls} onChange={e => setUrls(e.target.value)} placeholder="https://…" /></label>
    <div className="research-row"><label>Published timestamp<input value={published} onChange={e => setPublished(e.target.value)} placeholder="2026-10-26T12:00:00Z" /></label>
      <label>Observed timestamp<input value={observed} onChange={e => setObserved(e.target.value)} placeholder="2026-10-26T12:00:00Z" /></label></div>
    <button className="primary" disabled={loading}>Save entry</button>
    <small>Observations require a separate verification action and source references. Model interpretations stay in their own category.</small>
  </form>
}
function RulesPanel({market}: {market: ResearchMarket}): JSX.Element {
  const {request, loading} = useResearch()
  const [versions, setVersions] = useState<ResearchRules[]>([])
  const [changes, setChanges] = useState<ResearchRulesResult['changes']>({})
  const [selectedVersion, setSelectedVersion] = useState('')
  const [kind, setKind] = useState<string>('conditions')
  const [text, setText] = useState('')
  const [url, setUrl] = useState('')
  const id = market.identification.market_id
  useEffect(() => {
    let alive = true
    void window.research.request<ResearchRulesResult>({operation: 'rules', market: id}).then(result => { if (alive) { setVersions(result.versions); setChanges(result.changes || {}) } }).catch(() => undefined)
    return () => { alive = false }
  }, [id, market.rules, loading])
  const version = versions.find(v => String(v.rules_version_id) === selectedVersion) || market.rules
  return <section className="research-stack">
    <h2>Market rules & history</h2>
    <label>Rules version<select value={selectedVersion} onChange={e => setSelectedVersion(e.target.value)}><option value="">Current rules {market.rules ? `· v${market.rules.rules_version_id}` : 'unavailable'}</option>
      {versions.map(v => <option value={v.rules_version_id} key={v.rules_version_id}>v{v.rules_version_id} · {when(v.first_retrieved_at)}</option>)}
    </select></label>
    {version ? <>
      <pre className="verbatim">{version.text}</pre><small>Text SHA-256: {version.text_sha256}</small>
      <SourceLink url={version.api_url}>Public API source</SourceLink>{version.page_url && <SourceLink url={version.page_url}>Market page</SourceLink>}
      <p>Retrieved: {version.observations.map(at => when(at)).join(' · ')}</p>
      {version.resolution_source && <p>Public resolution source: {version.resolution_source}</p>}
      <p>Public resolution status: {version.resolution_status || 'Not reported'} · Trading end: {market.identification.trading_end || 'Unavailable'}</p>
      {changes[String(version.rules_version_id)] && <RulesChange change={changes[String(version.rules_version_id)]} />}
      <h3>Sourced annotations</h3>
      {version.annotations.length === 0 && <p className="muted">No established annotations. Trading dates do not establish resolution deadlines or measurement periods.</p>}
      {version.annotations.map(a => <article className="research-card" key={a.annotation_id}><strong>{a.kind}</strong>{a.needs_review && <span className="warning"> · Requires review</span>}<p>{a.text}</p><SourceLink url={a.source_url} /></article>)}
      <form className="research-form" onSubmit={e => {e.preventDefault(); attempt(async () => { await request({operation: 'annotate', market: id, version_id: version.rules_version_id, kind, text, source_url: url}); setText('') })}}>
        <label>Annotation kind<select value={kind} onChange={e => setKind(e.target.value)}>{ANNOTATIONS.map(k => <option key={k}>{k}</option>)}</select></label>
        <label>Established annotation<textarea value={text} required onChange={e => setText(e.target.value)} /></label>
        <label>Supporting source URL<input type="url" value={url} required onChange={e => setUrl(e.target.value)} /></label>
        <button disabled={loading}>Add annotation to v{version.rules_version_id}</button>
      </form>
    </> : <p className="warning">Market rules unavailable from the public source.</p>}
  </section>
}
function Relationships({market}: {market: ResearchMarket}): JSX.Element {
  const {request, loading} = useResearch()
  const [other, setOther] = useState('')
  const [kind, setKind] = useState<string>('related')
  const [text, setText] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [comparison, setComparison] = useState<ResearchPacketResult | null>(null)
  const id = market.identification.market_id
  return <section className="research-stack"><h2>Related contracts</h2>
    {market.relationships.map(r => <article key={r.relationship_id} className="research-card"><strong>{r.from_market} {['implication', 'causal', 'prerequisite'].includes(r.kind) ? '→' : '↔'} {r.to_market} · {r.kind}</strong><p>{r.explanation}</p>{r.source_url && <SourceLink url={r.source_url} />}</article>)}
    <form className="research-form" onSubmit={e => { e.preventDefault(); attempt(() => request({operation: 'relate', market: id, other_market: other, kind, text, ...(sourceUrl ? {source_url: sourceUrl} : {})})) }}>
      <label>Other contract · Gamma market ID<input required value={other} onChange={e => setOther(e.target.value)} /></label>
      <label>Relationship<select value={kind} onChange={e => setKind(e.target.value)}>{RELATIONSHIPS.map(k => <option key={k}>{k}</option>)}</select></label>
      <label>Explanation<textarea required value={text} onChange={e => setText(e.target.value)} /></label>
      <label>Source URL · optional<input type="url" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} /></label>
      <small>Implication, causal and prerequisite relationships point from this contract to the other contract. Correlation never implies causation.</small>
      <div className="research-row"><button disabled={loading}>Save relationship</button><button type="button" disabled={!other || loading} onClick={() => attempt(async () => setComparison(await request<ResearchPacketResult>({operation: 'compare', market: id, other_market: other})))}>Compare contracts</button></div>
    </form>
    {comparison && <div className="research-comparison">{comparison.packet.markets.map(m => <article className="research-card" key={m.identification.market_id}>
      <h3>{m.identification.question}</h3><p>Trading end: {m.identification.trading_end || 'Unavailable'}</p>
      <p>Rules version: {m.rules?.rules_version_id || 'Unavailable'}</p><p>Snapshot: {when(m.snapshot?.retrieved_at || null)}</p><Prices market={m} />
      {['resolution_deadline', 'measurement_period'].map(k => <p key={k}>{k}: {m.rules?.annotations.filter(a => a.kind === k && !a.needs_review).map(a => a.text).join('; ') || 'Not established'}</p>)}
      {m.warnings.map(w => <p key={w} className="warning">{w}</p>)}
    </article>)}</div>}
  </section>
}
function Exports({market}: {market: ResearchMarket}): JSX.Element {
  const {request, query, loading} = useResearch()
  const [scope, setScope] = useState('market')
  const [result, setResult] = useState<ResearchPacketResult | null>(null)
  const [format, setFormat] = useState<'shared.md' | 'canonical.json' | 'gpt.md' | 'claude.md'>('shared.md')
  const [copied, setCopied] = useState(false)
  return <section className="research-stack"><h2>Frozen research packet</h2><p>Canonical JSON and three Markdown files share one evidence snapshot. Refresh data before building when current quotes are needed.</p>
    <div className="research-row"><select aria-label="Packet scope" value={scope} onChange={e => setScope(e.target.value)}>
      <option value="market">This contract</option>{market.identification.event_id && <option value="event">Entire event</option>}{query.project && <option value="project">Current project</option>}<option value="followed">Followed markets</option>
    </select><button className="primary" disabled={loading} onClick={() => attempt(async () => {setResult(await request<ResearchPacketResult>({operation: 'packet', ...(scope === 'market' ? {market: market.identification.market_id} : scope === 'event' ? {event: market.identification.event_id!} : scope === 'project' ? {project: query.project} : {})})); setCopied(false)})}>Build & export four files</button>
      {scope === 'event' && <button disabled={loading} onClick={() => attempt(() => request({operation: 'refresh', event: market.identification.event_id!}))}>Refresh every event contract</button>}</div>
    {result && <><p className="success">Exported to {result.export?.directory}</p><small>Snapshot SHA-256: {result.snapshot_sha256}</small><p>Generated {when(result.packet.generated_at)}</p>
      <div className="research-row"><select aria-label="Packet format" value={format} onChange={e => {setFormat(e.target.value as typeof format); setCopied(false)}}>{Object.keys(result.contents).map(f => <option key={f}>{f}</option>)}</select>
        <button onClick={() => attempt(async () => {await window.pm.writeClipboard(result.contents[format]); setCopied(true)})}>{copied ? 'Copied' : 'Copy to clipboard'}</button>
        <button disabled={loading} onClick={() => attempt(async () => setResult(await request<ResearchPacketResult>({operation: 'render', packet_id: result.packet_id})))}>Render same snapshot</button></div>
      <pre className="packet-preview">{result.contents[format]}</pre></>}
  </section>
}
function MarketDetail({market}: {market: ResearchMarket}): JSX.Element {
  const {request, loading, data} = useResearch()
  const [tab, setTab] = useState('Overview')
  const [tags, setTags] = useState(market.tags.join(', '))
  const [project, setProject] = useState('default')
  const id = market.identification.market_id
  return <div className="research-detail"><header><div className="research-eyebrow">GAMMA {id} · {market.identification.lifecycle} · {market.identification.protocol || 'protocol unavailable'}</div><h1>{market.identification.question}</h1>
    <div className="research-row"><select aria-label="Research status" value={market.status} disabled={loading} onChange={e => attempt(() => request({operation: 'status', market: id, status: e.target.value}))}>{STATUSES.map(s => <option key={s}>{s}</option>)}</select>
      <button disabled={loading} onClick={() => attempt(() => request({operation: 'refresh', market: id}))}>Refresh public data</button>
      <button disabled={loading} onClick={() => attempt(() => request({operation: market.followed ? 'unfollow' : 'refollow', market: id}))}>{market.followed ? 'Unfollow' : 'Follow again'}</button>
      <button disabled={loading} onClick={() => attempt(() => request({operation: market.status === 'archived' ? 'unarchive' : 'archive', market: id}))}>{market.status === 'archived' ? 'Unarchive' : 'Archive'}</button>
    </div><p className="muted">Last public metadata: {when(market.last_success_at)}</p>
  </header><nav className="research-tabs">{['Overview', 'Book', 'Rules', 'Research', 'Relationships', 'Exports'].map(t => <button className={tab === t ? 'selected' : ''} key={t} onClick={() => setTab(t)}>{t}</button>)}</nav>
  {tab === 'Overview' && <section className="research-stack"><PriceHistoryPanel market={market} /><Prices market={market} />
    <div className="research-comparison"><ActivityCard activity={data.activity[id]} /><EventContextCard event={market.identification.event_id ? data.events[market.identification.event_id] : undefined} /></div>
    <div className="research-card"><h3>Identification & timing</h3><dl><dt>Event ID</dt><dd>{market.identification.event_id || 'Unavailable'}</dd><dt>Condition ID</dt><dd>{market.identification.condition_id || 'Unavailable'}</dd><dt>Question ID</dt><dd>{market.identification.question_id || 'Unavailable'}</dd><dt>Trading start</dt><dd>{market.identification.trading_start || 'Unavailable'}</dd><dt>Trading end</dt><dd>{market.identification.trading_end || 'Unavailable'}</dd></dl><small>Trading dates do not establish a resolution deadline. Establish measurement periods in sourced rules annotations.</small>{market.identification.page_url && <SourceLink url={market.identification.page_url}>Open market page ↗</SourceLink>}</div>
    <form className="research-row" onSubmit={e => {e.preventDefault(); attempt(() => request({operation: 'tags', market: id, tags: tags.split(',').map(t => t.trim()).filter(Boolean)}))}}><label>Tags · comma separated<input value={tags} onChange={e => setTags(e.target.value)} /></label><button disabled={loading}>Save tags</button></form>
    <div className="research-card"><h3>Projects</h3>{market.projects.map(p => <div className="research-row" key={p}><span>{p}</span><button disabled={loading} onClick={() => attempt(() => request({operation: 'project_remove', project: p, market: id}))}>Remove membership</button></div>)}
      <div className="research-row"><select aria-label="Project membership" value={project} onChange={e => setProject(e.target.value)}>{data.projects.map(p => <option key={p.name}>{p.name}</option>)}</select><button disabled={loading} onClick={() => attempt(() => request({operation: 'project_add', project, market: id}))}>Add to project</button></div></div>
    {[...market.warnings, ...(market.snapshot?.warnings || [])].map((w, i) => <p className="warning" key={`${i}:${w}`}>{w}</p>)}
    {market.snapshot?.quotes.map(q => <article key={q.outcome_id} className="research-card"><strong>Outcome {q.outcome_id}</strong><p>Book retrieved: {when(q.book_retrieved_at)}</p><p>Midpoint retrieved: {when(q.midpoint_retrieved_at)}</p><p>Last trade retrieved: {when(q.last_trade_retrieved_at)}</p>{q.warnings.map(w => <p className="warning" key={w}>{w}</p>)}</article>)}
  </section>}
  {tab === 'Book' && <BookPanel market={market} />}
  {tab === 'Rules' && <RulesPanel market={market} />}
  {tab === 'Research' && <section className="research-stack"><h2>Research entries</h2><EntryForm market={market} />{market.entries.map(e => <article key={e.entry_id} className="research-card"><div className="research-row"><strong>{e.category}</strong><small>{when(e.created_at)}</small></div><p className="preserve">{e.text}</p>{e.sources.map((s, i) => <div key={`${i}:${s.url}`}><SourceLink url={s.url} /><small>Published {s.published_at || 'unknown'} · Observed {s.observed_at || 'unknown'}</small></div>)}{e.verified_at ? <p className="success">User verified · {when(e.verified_at)}</p> : e.category === 'observation' && <button disabled={!e.sources.length || loading} onClick={() => attempt(() => request({operation: 'verify', entry_id: e.entry_id}))}>Mark observation verified</button>}</article>)}</section>}
  {tab === 'Relationships' && <Relationships market={market} />}{tab === 'Exports' && <Exports market={market} />}
  </div>
}
function RowPrice({market, change}: {market: ResearchMarket; change: number | null | undefined}): JSX.Element | null {
  const outcome = market.identification.outcomes[0]
  const quote = market.snapshot?.quotes.find(q => q.outcome_id === outcome?.outcome_id)
  if (!outcome || quote?.displayed_price == null) return null
  return <em className="row-price">{outcome.label} {px(quote.displayed_price)}{change != null && <b className={change > 0 ? 'up' : change < 0 ? 'down' : ''}> {signedPx(change)} 24h</b>}</em>
}
export function ResearchScreen(): JSX.Element {
  const {data, query, setQuery, request, loading, error} = useResearch()
  const [reference, setReference] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [discovery, setDiscovery] = useState<ResearchDiscovery | null>(null)
  const [projectName, setProjectName] = useState('')
  const market = data.markets.find(m => m.identification.market_id === selected) || data.markets[0]
  return <main className="research-app">
    <div className="research-toolbar"><form className="research-search" onSubmit={e => {e.preventDefault(); attempt(async () => setDiscovery(await request<ResearchDiscovery>({operation: 'search', reference})))}}>
      <input aria-label="Search or public reference" required value={reference} onChange={e => setReference(e.target.value)} placeholder="Search public markets or paste a Polymarket URL…" />
      <button disabled={loading}>Search</button><button type="button" disabled={loading || !reference} className="primary" onClick={() => attempt(async () => {const result = await request<{market_ids: string[]}>({operation: 'follow', reference, project: query.project || 'default'}); setSelected(result.market_ids[0]); setDiscovery(null)})}>Follow URL / ID</button>
    </form><div className="research-row"><select aria-label="Project filter" value={query.project || ''} onChange={e => setQuery(e.target.value ? {project: e.target.value} : {})}><option value="">Followed markets</option>{data.projects.map(p => <option value={p.name} key={p.name}>{p.name}</option>)}</select><button aria-pressed={!!query.all_markets} onClick={() => setQuery(query.all_markets ? {} : {all_markets: true})}>All saved</button>
      <button disabled={loading} onClick={() => attempt(() => request(query.project ? {operation: 'refresh', project: query.project} : {operation: 'refresh'}))}>{query.project ? 'Refresh project' : 'Refresh followed'}</button></div></div>
    {error && <div className="research-error" role="alert">{error}</div>}{loading && <div className="research-progress" role="status">Working… public requests may take a moment.</div>}
    {discovery && <section className="research-results"><div className="research-row"><h2>Public search results</h2><button onClick={() => setDiscovery(null)}>Close</button></div>
      {discovery.events.map(e => <article key={e.event_id}><strong>{e.title}</strong><span>{e.expected_market_ids.length} contracts</span><button disabled={loading} onClick={() => attempt(async () => {await request({operation: 'follow', reference: `event:${e.event_id}`, project: query.project || 'default'}); setDiscovery(null)})}>Follow entire event</button></article>)}
      {discovery.markets.map(m => <article key={m.identification.market_id}><span>{m.identification.question}</span><button disabled={loading} onClick={() => attempt(async () => {await request({operation: 'follow', reference: `market:${m.identification.market_id}`, project: query.project || 'default'}); setSelected(m.identification.market_id); setDiscovery(null)})}>Follow contract</button></article>)}
      {discovery.events.length === 0 && <p>No public matches.</p>}{discovery.warnings.map(w => <p key={w}>{w}</p>)}
    </section>}
    <div className="research-layout"><aside className="research-sidebar"><div className="research-eyebrow">{data.markets.length} CONTRACTS</div>
      {data.markets.map(m => <button className={`market-row ${market?.identification.market_id === m.identification.market_id ? 'selected' : ''}`} key={m.identification.market_id} onClick={() => setSelected(m.identification.market_id)}><strong>{m.identification.question}</strong><RowPrice market={m} change={data.activity[m.identification.market_id]?.price_change_1d} /><span>{m.status} · {m.identification.lifecycle}</span><small>{m.tags.join(' · ')}</small></button>)}
      <form className="research-form project-form" onSubmit={e => {e.preventDefault(); attempt(async () => {await request({operation: 'project_create', project: projectName}); setProjectName('')})}}><label>New project<input required value={projectName} onChange={e => setProjectName(e.target.value)} placeholder="Project name" /></label><button disabled={loading}>Create project</button></form>
    </aside><div className="research-content">{market ? <MarketDetail market={market} key={market.identification.market_id} /> : <div className="research-empty"><div className="research-eyebrow">YOUR PUBLIC RESEARCH WORKSPACE</div><h1>Start with a market question.</h1><p>Search for an event, or paste a public Polymarket URL and follow it.</p><p>Collect outcome prices and verbatim rules, record sourced research, and export the same evidence to GPT and Claude.</p><small>This workspace starts empty. No account connection is needed.</small></div>}</div></div>
    <footer className="research-footer">PUBLIC DATA · LOCAL RESEARCH <span>Manual evidence verification · Manual model handoffs</span></footer>
  </main>
}
