// Shared mock data for all three Polyberg Terminal directions.
// Mirrors the shapes implied by polyberg: market_registry.yaml,
// portfolio_current.yaml, open_orders.yaml, recent_catalysts.md, snapshots.

window.pmData = (function () {
  const markets = [
    {
      id: 'hormuz_normal_may15',
      name: 'Strait of Hormuz remains open through May 15',
      url: 'polymarket.com/event/hormuz-normal-may15',
      category: 'Geopolitics',
      ruleKey: 'hormuz_open_v2',
      oracle: 'UMA optimistic',
      preferredSide: 'YES',
      resolutionDate: '2026-05-15T16:00:00Z',
      ruleRisk: 'medium',
      mark: 0.78,
      bid: 0.77,
      ask: 0.79,
      spread: 2,
      liq: 184_200,
      hist: [0.62,0.64,0.63,0.66,0.69,0.68,0.71,0.74,0.73,0.76,0.78,0.79,0.78],
      lastUpdate: '2026-05-08T13:42:11Z',
      snapshotAge: 18,
      ruleText:
        'Resolves YES if no state-actor-imposed closure of the Strait of Hormuz to ' +
        'commercial shipping is in effect at 16:00 UTC on May 15, 2026, per UMA ' +
        'optimistic oracle adjudication. A closure is defined as a publicly ' +
        'declared interdiction lasting ≥ 6 consecutive hours and confirmed by at ' +
        'least two of: USNI, Lloyd\'s List Intelligence, or Reuters maritime desk. ' +
        'Naval incidents short of declared closure (boardings, seizures of single ' +
        'vessels, drone exchanges) DO NOT trigger NO resolution.',
      ruleRiskNotes: [
        'Oracle has 48h dispute window; YES paid out only after window closes.',
        'Ambiguity: a partial / single-flag closure has been disputed in 2024 SoH market.',
      ],
      catalysts: [
        { t: '2026-05-08 09:14Z', src: 'Reuters', txt: 'Iranian FM: "open dialogue continues" — calls de-escalation language deliberate' },
        { t: '2026-05-07 22:00Z', src: 'USNI', txt: 'USS Carney completes northbound transit, no challenge reported' },
        { t: '2026-05-06 17:30Z', src: 'Lloyd\'s', txt: 'War-risk premia for Gulf-bound VLCCs flat WoW at 0.45%' },
      ],
    },
    {
      id: 'cl_high_120_end_june',
      name: 'Crude oil (Brent) ≥ $120 at June 30 close',
      url: 'polymarket.com/event/cl-high-120-end-june',
      category: 'Commodities',
      ruleKey: 'brent_settle_120',
      oracle: 'UMA optimistic',
      preferredSide: 'NO',
      resolutionDate: '2026-06-30T20:00:00Z',
      ruleRisk: 'low',
      mark: 0.32,
      bid: 0.31,
      ask: 0.33,
      spread: 2,
      liq: 412_900,
      hist: [0.41,0.39,0.40,0.38,0.36,0.37,0.35,0.34,0.33,0.34,0.32,0.31,0.32],
      lastUpdate: '2026-05-08T13:41:50Z',
      snapshotAge: 18,
      ruleText:
        'Resolves YES if the ICE Brent front-month settlement on June 30, 2026 ' +
        '(or, if June 30 is not a settlement day, the next preceding settlement ' +
        'day) is ≥ $120.00 USD/bbl, sourced from ICE official settlement notice.',
      ruleRiskNotes: [
        'Front-month roll mid-June: convention is to use whichever contract is ' +
        'front-month on settlement day, not the strip held continuously.',
      ],
      catalysts: [
        { t: '2026-05-08 11:02Z', src: 'IEA', txt: 'Demand outlook revised -340kbpd Q3 on China industrial slack' },
        { t: '2026-05-07 18:45Z', src: 'EIA', txt: 'Crude inventories +3.1 Mbbl vs +0.4 expected' },
        { t: '2026-05-05 14:10Z', src: 'OPEC+', txt: 'Production hike of 200kbpd reaffirmed for July' },
      ],
    },
    {
      id: 'trump_blockade_lifted_apr30',
      name: 'US Gulf shipping advisory lifted before April 30',
      url: 'polymarket.com/event/trump-blockade-lifted-apr30',
      category: 'Geopolitics',
      ruleKey: 'gulf_advisory_lifted',
      oracle: 'UMA optimistic',
      preferredSide: 'YES',
      resolutionDate: '2026-04-30T23:59:00Z',
      ruleRisk: 'high',
      mark: 0.42,
      bid: 0.40,
      ask: 0.44,
      spread: 4,
      liq: 58_300,
      hist: [0.55,0.58,0.54,0.51,0.49,0.46,0.48,0.47,0.45,0.44,0.42,0.41,0.42],
      lastUpdate: '2026-05-08T13:39:02Z',
      snapshotAge: 21,
      ruleText:
        'Resolves YES if the US Department of State Maritime Advisory 2026-A07 is ' +
        'either (a) formally rescinded, or (b) downgraded below "Level 3 — ' +
        'Reconsider Travel" by 23:59 UTC April 30, 2026. Statements by individual ' +
        'officials short of an official advisory revision DO NOT count.',
      ruleRiskNotes: [
        'High rule risk: market has been extended once already (original deadline Apr 15).',
        'UMA dispute likely if downgrade language ambiguous.',
      ],
      catalysts: [
        { t: '2026-05-08 06:00Z', src: 'State Dept', txt: 'No update to Advisory 2026-A07; status review noted on internal calendar' },
        { t: '2026-05-04 13:20Z', src: 'WSJ', txt: 'Officials privately skeptical of timeline — "weeks, not days"' },
      ],
    },
  ];

  const positions = [
    { marketId: 'hormuz_normal_may15',         side: 'YES', shares: 1240, avg: 0.71, mark: 0.78, dayPnl:  18.60 },
    { marketId: 'cl_high_120_end_june',        side: 'NO',  shares:  800, avg: 0.66, mark: 0.68, dayPnl:  +6.40 },
    { marketId: 'trump_blockade_lifted_apr30', side: 'YES', shares:  600, avg: 0.51, mark: 0.42, dayPnl: -12.00 },
  ];

  const openOrders = [
    { id: 'o-9132', marketId: 'hormuz_normal_may15',         side: 'YES', kind: 'BUY',  px: 0.74, qty: 500,  status: 'WORKING', placed: '2026-05-08T11:02:13Z' },
    { id: 'o-9133', marketId: 'hormuz_normal_may15',         side: 'YES', kind: 'BUY',  px: 0.65, qty: 1000, status: 'WORKING', placed: '2026-05-07T22:14:00Z' },
    { id: 'o-9128', marketId: 'cl_high_120_end_june',        side: 'NO',  kind: 'SELL', px: 0.74, qty: 400,  status: 'WORKING', placed: '2026-05-08T08:50:31Z' },
    { id: 'o-9119', marketId: 'trump_blockade_lifted_apr30', side: 'YES', kind: 'BUY',  px: 0.36, qty: 800,  status: 'WORKING', placed: '2026-05-06T19:45:11Z' },
  ];

  // Workflow stages mirror the CLI surface
  const workflow = [
    { id: 'context',   label: 'Update context',     state: 'stale',   ts: '2026-05-07 22:14',  cli: 'edit context/' },
    { id: 'packet',    label: 'Build packet',       state: 'ok',      ts: '2026-05-08 13:00',  cli: 'build-packet' },
    { id: 'validate',  label: 'Validate response',  state: 'ok',      ts: '2026-05-08 13:18',  cli: 'validate-response' },
    { id: 'adj-in',    label: 'Build adjudicator',  state: 'ok',      ts: '2026-05-08 13:21',  cli: 'build-adjudicator-input' },
    { id: 'adj-val',   label: 'Validate adjudicator', state: 'pending', ts: '—',                cli: 'validate-adjudicator' },
    { id: 'ticket',    label: 'Build trade ticket', state: 'pending', ts: '—',                  cli: 'build-trade-ticket' },
  ];

  // Top-of-screen "fresh / stale" audit (the freshness audit from packet_builder)
  const freshness = [
    { file: 'live_state.yaml',         age:  3,  state: 'fresh' },
    { file: 'portfolio_current.yaml',  age: 18,  state: 'fresh' },
    { file: 'open_orders.yaml',        age: 18,  state: 'fresh' },
    { file: 'recent_catalysts.md',     age: 41,  state: 'aging' },
    { file: 'market_registry.yaml',    age: 312, state: 'fresh' },
    { file: 'snapshots/2026-05-08T13', age: 18,  state: 'fresh' },
  ];

  const liveState = {
    mode: 'RESEARCH',
    cash: 2840.00,
    thesis:
      'Hormuz status-quo bias persists; SoH YES underpriced relative to historical ' +
      'closure base rates. Brent $120 NO is a slow-bleed on demand-side data. Trump ' +
      'advisory rescission is a fade — high rule risk + soft deadline.',
    constraints: [
      'No single-market exposure > 30% of equity',
      'No new entries with < 7 days to resolution',
      'NO orders > $0.85 without explicit thesis revision',
    ],
    notes: 'Pulled authenticated read-only positions at 13:42Z; no diffs vs canonical.',
  };

  const equity = liveState.cash + positions.reduce((a, p) => a + p.shares * p.mark, 0);
  const dayPnl = positions.reduce((a, p) => a + p.dayPnl, 0);
  const totalPnl = positions.reduce((a, p) => a + (p.mark - p.avg) * p.shares, 0);

  // 24h price-change heat strip across the 9 markets we 'watch' — exaggerated
  // beyond positions to make the strip feel populated.
  const heat = [
    { id: 'hormuz_normal_may15',  d: +2.6 },
    { id: 'cl_high_120_end_june', d: -1.8 },
    { id: 'trump_blockade_lifted_apr30', d: -3.4 },
    { id: 'fed_cut_jun_25bp',     d: +0.8 },
    { id: 'btc_120k_eoy',         d: +1.2 },
    { id: 'taiwan_drill_q2',      d: -0.4 },
    { id: 'cpi_apr_above_3',      d: +0.5 },
    { id: 'ukraine_ceasefire_q3', d: -2.1 },
    { id: 'house_majority_dem',   d: +0.3 },
  ];

  function fmtUsd(n, signed) {
    const s = (signed && n > 0) ? '+' : '';
    return s + (n < 0 ? '-' : '') + '$' + Math.abs(n).toFixed(2)
      .replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  function fmtPct(n, signed) { return (signed && n > 0 ? '+' : '') + n.toFixed(2) + '%'; }
  function fmtCents(n) { return (n * 100).toFixed(1) + '¢'; }

  // Intake — pasted tweets, articles, notes that haven't been promoted to
  // recent_catalysts.md yet. The "Run next stage" button on the dashboard
  // also ingests this queue: each item gets auto-suggested a market tag,
  // user confirms, and the rebuild appends entries to recent_catalysts.md
  // keyed by market.
  const intake = [
    {
      id: 'in-0008', kind: 'tweet', addedAt: '2026-05-08 13:48Z',
      author: '@maritimebrief', url: 'x.com/maritimebrief/status/1788…',
      text: 'IRGCN small-boat activity at Larak Is. cluster up sharply on AIS — third day. Not a closure pattern but heat is climbing. War-risk premia still flat, which is the tell.',
      suggestedMarket: 'hormuz_normal_may15', suggestionConfidence: 0.86, status: 'suggested',
    },
    {
      id: 'in-0007', kind: 'article', addedAt: '2026-05-08 12:30Z',
      author: 'Bloomberg', url: 'bloomberg.com/news/articles/2026-05-08/iea-cuts-q3-demand',
      text: 'IEA Q3 demand outlook cut another 120kbpd; cites weaker Chinese petrochem runs. Front-month Brent screens softer into the European close.',
      suggestedMarket: 'cl_high_120_end_june', suggestionConfidence: 0.91, status: 'suggested',
    },
    {
      id: 'in-0006', kind: 'note', addedAt: '2026-05-08 11:55Z',
      author: 'me', url: '',
      text: 'Worth tracking: the State Dept advisory review cycle historically clusters near month-end. If no movement by 5/12 close I want to fade harder.',
      suggestedMarket: 'trump_blockade_lifted_apr30', suggestionConfidence: 0.74, status: 'suggested',
    },
    {
      id: 'in-0005', kind: 'tweet', addedAt: '2026-05-08 10:12Z',
      author: '@energy_obs', url: 'x.com/energy_obs/status/1788…',
      text: 'OPEC+ delegates: production hike timeline holds for July. Some grumbling from KSA on compliance gaps but no formal pushback.',
      suggestedMarket: 'cl_high_120_end_june', suggestionConfidence: 0.79, status: 'confirmed',
    },
  ];

  // Snapshot history — each row points at a snapshots/<ts>.json file we
  // imported. The diff column comes from comparing to the previous snapshot
  // for the same market. Used by the snapshot history screen.
  const snapshots = [
    { ts: '2026-05-08T13-24Z', file: 'snapshots/2026-05-08T13-24Z.json', markets: 9, diffsCount: 4, missingInfo: 0, freshMin: 18 },
    { ts: '2026-05-08T09-08Z', file: 'snapshots/2026-05-08T09-08Z.json', markets: 9, diffsCount: 2, missingInfo: 0, freshMin: 0 },
    { ts: '2026-05-07T22-14Z', file: 'snapshots/2026-05-07T22-14Z.json', markets: 9, diffsCount: 3, missingInfo: 1, freshMin: 0 },
    { ts: '2026-05-07T16-02Z', file: 'snapshots/2026-05-07T16-02Z.json', markets: 9, diffsCount: 5, missingInfo: 0, freshMin: 0 },
    { ts: '2026-05-07T09-30Z', file: 'snapshots/2026-05-07T09-30Z.json', markets: 9, diffsCount: 1, missingInfo: 2, freshMin: 0 },
    { ts: '2026-05-06T22-01Z', file: 'snapshots/2026-05-06T22-01Z.json', markets: 9, diffsCount: 2, missingInfo: 0, freshMin: 0 },
  ];

  // Forward-looking: Grok-driven sentiment per market. Stub now, real later.
  // Shape kept small so the UI can light up immediately when data appears.
  const sentiment = {
    enabled: false, // toggled when grok integration lands
    source:  'grok-3 · X firehose',
    asOf:    null,
    perMarket: {
      hormuz_normal_may15:        { score: null, n: 0, lean: null },
      cl_high_120_end_june:       { score: null, n: 0, lean: null },
      trump_blockade_lifted_apr30:{ score: null, n: 0, lean: null },
    },
  };

  // Light keyword router for auto-tagging pasted items into a market.
  const tagRules = [
    { id: 'hormuz_normal_may15',         kw: ['hormuz','strait','soh','irgcn','larak','tanker','vlcc'] },
    { id: 'cl_high_120_end_june',        kw: ['brent','crude','wti','iea','eia','opec','petrochem','demand'] },
    { id: 'trump_blockade_lifted_apr30', kw: ['advisory','state dept','state department','blockade','gulf advisory','rescind','downgrade'] },
  ];
  function suggestMarket(text) {
    const t = (text || '').toLowerCase();
    let best = { id: null, score: 0 };
    tagRules.forEach(r => {
      const hits = r.kw.filter(k => t.includes(k)).length;
      if (hits > best.score) best = { id: r.id, score: hits };
    });
    if (!best.id) return { id: null, confidence: 0 };
    // crude confidence: 1 hit ≈ 0.55, 2 ≈ 0.78, 3+ ≈ 0.92
    const conf = Math.min(0.95, 0.4 + best.score * 0.18);
    return { id: best.id, confidence: conf };
  }

  return {
    markets, positions, openOrders, workflow, freshness, liveState,
    equity, dayPnl, totalPnl, heat,
    intake, snapshots, sentiment,
    fmtUsd, fmtPct, fmtCents, suggestMarket,
    marketById: id => markets.find(m => m.id === id),
  };
})();
