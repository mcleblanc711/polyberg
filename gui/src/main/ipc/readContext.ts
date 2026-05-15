import { readFileSync, readdirSync } from 'fs'
import { resolve } from 'path'
import yaml from 'js-yaml'
import {
  ageMinutes,
  CONTEXT_DIR,
  REPO_ROOT,
  REPORTS_DIR,
  SNAPSHOTS_DIR
} from './repo'
import {
  EMPTY_PRICE_WINDOWS,
  type AccountImport,
  type AccountImportFile,
  type FreshnessEntry,
  type FreshnessState,
  type Market,
  type Mode,
  type OpenOrder,
  type PmDataPayload,
  type Position,
  type PriceWindow,
  type PriceWindows,
  type RuleRisk,
  type Side,
  type SnapshotMeta,
  type WorkflowStage,
  type WorkflowState
} from '../../shared/contract'

const loadYaml = <T>(path: string): T | null => {
  try {
    return yaml.load(readFileSync(path, 'utf8')) as T
  } catch {
    return null
  }
}

const asString = (v: unknown, fallback = ''): string =>
  typeof v === 'string' ? v : fallback

const asNumber = (v: unknown, fallback = 0): number =>
  typeof v === 'number' && Number.isFinite(v) ? v : fallback

const asSide = (v: unknown): Side => (v === 'YES' || v === 'NO' ? v : 'NO')

const asRuleRisk = (v: unknown): RuleRisk =>
  v === 'low' || v === 'medium' || v === 'high' ? v : 'medium'

const MODE_MAP: Record<string, Mode> = {
  research_only: 'RESEARCH',
  research: 'RESEARCH',
  trading: 'TRADING',
  paused: 'PAUSED'
}

const freshnessFor = (mins: number): FreshnessState =>
  mins < 120 ? 'fresh' : mins < 1440 ? 'aging' : 'stale'

interface RegistryFile {
  markets?: Array<{
    market_id?: string
    name?: string
    polymarket_url?: string
    category?: string
    rule_key?: string
    oracle_type?: string
    preferred_side?: string
    resolution_date?: string
    notes?: string
    risk_flags?: string[]
    rule_risk?: { dispute_risk?: string }
  }>
}

interface PortfolioFile {
  positions?: Array<{
    market_id?: string
    side?: string
    avg_price?: number
    mark_price?: number
    shares?: number
  }>
  cash_available?: number
}

interface OpenOrdersFile {
  as_of?: string
  buy_orders?: Array<{ market_id?: string; side?: string; price?: number; shares?: number }>
  sell_orders?: Array<{ market_id?: string; side?: string; price?: number; shares?: number }>
}

interface LiveStateFile {
  mode?: string
  cash_available?: number
  account_snapshot?: { cash_available?: number }
  active_thesis?: string[] | string
  constraints?: Record<string, unknown> | string[]
  notes?: string[] | string
  proxy_wallet?: string
}

interface PriceHistoryFile {
  as_of?: string
  markets?: Record<
    string,
    {
      yes_token_id?: string
      series?: Array<{ t?: number; p?: number }>
      windows?: Record<string, { high?: number; low?: number }>
    }
  >
}

const readMarkets = (): Market[] => {
  const data = loadYaml<RegistryFile>(resolve(CONTEXT_DIR, 'market_registry.yaml'))
  const rows = data?.markets ?? []
  return rows
    .filter((r) => typeof r.market_id === 'string' && r.market_id.length > 0)
    .map((r) => ({
      id: asString(r.market_id),
      name: asString(r.name, asString(r.market_id)),
      url: asString(r.polymarket_url),
      category: asString(r.category),
      ruleKey: asString(r.rule_key),
      oracle: asString(r.oracle_type),
      preferredSide: asSide(r.preferred_side),
      resolutionDate: asString(r.resolution_date),
      ruleRisk: asRuleRisk(r.rule_risk?.dispute_risk),
      mark: 0,
      bid: 0,
      ask: 0,
      spread: 0,
      liq: 0,
      hist: [],
      windows: EMPTY_PRICE_WINDOWS,
      windowsAsOf: '',
      lastUpdate: '',
      snapshotAge: 0,
      ruleText: asString(r.notes),
      ruleRiskNotes: Array.isArray(r.risk_flags) ? r.risk_flags.filter((s): s is string => typeof s === 'string') : [],
      catalysts: []
    }))
}

const readPriceHistory = (): { asOf: string; windowsById: Map<string, PriceWindows> } => {
  let raw: PriceHistoryFile | null = null
  try {
    raw = JSON.parse(readFileSync(resolve(CONTEXT_DIR, 'price_history.json'), 'utf8'))
  } catch {
    return { asOf: '', windowsById: new Map() }
  }
  const asOf = asString(raw?.as_of)
  const windowsById = new Map<string, PriceWindows>()
  const markets = raw?.markets ?? {}
  for (const [marketId, entry] of Object.entries(markets)) {
    const w = entry?.windows ?? {}
    const pick = (key: string): PriceWindow => {
      const v = w[key]
      return { high: asNumber(v?.high), low: asNumber(v?.low) }
    }
    windowsById.set(marketId, { d1: pick('d1'), w1: pick('w1'), m1: pick('m1') })
  }
  return { asOf, windowsById }
}

const ACCOUNT_DIR = resolve(REPORTS_DIR, 'account')

const readAccountImportFile = (
  candidateFilenames: string[],
  canonicalFilename: string
): AccountImportFile => {
  const filename = candidateFilenames[0] ?? ''
  const base: AccountImportFile = {
    filename,
    exists: false,
    asOf: '',
    source: '',
    payloadJson: '',
    canonicalText: '',
    canonicalFilename
  }
  try {
    base.canonicalText = readFileSync(resolve(CONTEXT_DIR, canonicalFilename), 'utf8')
  } catch {
    base.canonicalText = ''
  }
  for (const candidate of candidateFilenames) {
    try {
      const raw = readFileSync(resolve(ACCOUNT_DIR, candidate), 'utf8')
      const parsed = JSON.parse(raw) as { as_of?: unknown; source?: unknown; payload?: unknown }
      base.filename = candidate
      base.exists = true
      base.asOf = asString(parsed?.as_of)
      base.source = asString(parsed?.source)
      base.payloadJson = JSON.stringify(parsed?.payload ?? parsed ?? null, null, 2)
      break
    } catch {
      // try next candidate
    }
  }
  return base
}

const readAccountImport = (): AccountImport => ({
  positions: readAccountImportFile(
    ['positions_data_api.json', 'positions_raw.json'],
    'portfolio_current.yaml'
  ),
  balances: readAccountImportFile(
    ['usdc_balance.json', 'balances_raw.json'],
    'portfolio_current.yaml'
  ),
  openOrders: readAccountImportFile(
    ['open_orders_clob.json', 'open_orders_raw.json'],
    'open_orders.yaml'
  )
})

const applyPriceHistory = (markets: Market[]): Market[] => {
  const { asOf, windowsById } = readPriceHistory()
  if (windowsById.size === 0) return markets
  return markets.map((m) => {
    const w = windowsById.get(m.id)
    return w ? { ...m, windows: w, windowsAsOf: asOf } : m
  })
}

const readPositions = (markets: Market[]): Position[] => {
  const data = loadYaml<PortfolioFile>(resolve(CONTEXT_DIR, 'portfolio_current.yaml'))
  const known = new Set(markets.map((m) => m.id))
  return (data?.positions ?? [])
    .filter((p) => typeof p.market_id === 'string' && known.has(p.market_id))
    .map((p) => ({
      marketId: asString(p.market_id),
      side: asSide(p.side),
      shares: asNumber(p.shares),
      avg: asNumber(p.avg_price),
      mark: asNumber(p.mark_price),
      dayPnl: 0
    }))
}

const readPortfolioCash = (): number | null => {
  const data = loadYaml<PortfolioFile>(resolve(CONTEXT_DIR, 'portfolio_current.yaml'))
  if (data && typeof data.cash_available === 'number') return data.cash_available
  return null
}

const readOpenOrders = (markets: Market[]): OpenOrder[] => {
  const data = loadYaml<OpenOrdersFile>(resolve(CONTEXT_DIR, 'open_orders.yaml'))
  if (!data) return []
  const placed = asString(data.as_of)
  const known = new Set(markets.map((m) => m.id))
  const rows: OpenOrder[] = []
  ;(data.buy_orders ?? []).forEach((o, i) => {
    if (!o.market_id || !known.has(o.market_id)) return
    rows.push({
      id: `o-buy-${i}`,
      marketId: asString(o.market_id),
      side: asSide(o.side),
      kind: 'BUY',
      px: asNumber(o.price),
      qty: asNumber(o.shares),
      status: 'WORKING',
      placed
    })
  })
  ;(data.sell_orders ?? []).forEach((o, i) => {
    if (!o.market_id || !known.has(o.market_id)) return
    rows.push({
      id: `o-sell-${i}`,
      marketId: asString(o.market_id),
      side: asSide(o.side),
      kind: 'SELL',
      px: asNumber(o.price),
      qty: asNumber(o.shares),
      status: 'WORKING',
      placed
    })
  })
  return rows
}

const readLiveState = () => {
  const data = loadYaml<LiveStateFile>(resolve(CONTEXT_DIR, 'live_state.yaml'))
  const modeKey = asString(data?.mode, 'research_only').toLowerCase()
  const mode: Mode = MODE_MAP[modeKey] ?? 'RESEARCH'
  // Prefer portfolio_current.yaml's cash_available — that's the freshly-promoted
  // value from import-clob-balance + promote-positions. live_state.yaml's cash
  // is a manual snapshot, kept only as fallback for users without CLOB auth.
  const portfolioCash = readPortfolioCash()
  const cash =
    portfolioCash !== null
      ? portfolioCash
      : asNumber(data?.cash_available ?? data?.account_snapshot?.cash_available)
  const thesisRaw = data?.active_thesis
  const thesis = Array.isArray(thesisRaw) ? thesisRaw.join(' ') : asString(thesisRaw)
  let constraints: string[] = []
  if (Array.isArray(data?.constraints)) {
    constraints = data.constraints.filter((s): s is string => typeof s === 'string')
  } else if (data?.constraints && typeof data.constraints === 'object') {
    constraints = Object.entries(data.constraints)
      .filter(([, v]) => v === true)
      .map(([k]) => k.replace(/_/g, ' '))
  }
  const notesRaw = data?.notes
  const notes = Array.isArray(notesRaw) ? notesRaw.join('\n') : asString(notesRaw)
  const proxyWallet = asString(data?.proxy_wallet)
  return { mode, cash, thesis, constraints, notes, proxyWallet }
}

const FRESH_FILES = [
  'live_state.yaml',
  'portfolio_current.yaml',
  'open_orders.yaml',
  'recent_catalysts.md',
  'market_registry.yaml',
  'trading_principles.md',
  'stable_rules.md'
]

const readFreshness = (): FreshnessEntry[] =>
  FRESH_FILES.map((f) => {
    const age = ageMinutes(resolve(CONTEXT_DIR, f)) ?? Number.MAX_SAFE_INTEGER
    return { file: f, age, state: freshnessFor(age) }
  })

const readSnapshots = (): SnapshotMeta[] => {
  let names: string[]
  try {
    names = readdirSync(SNAPSHOTS_DIR).filter((n) => n.endsWith('.json'))
  } catch {
    return []
  }
  return names
    .sort((a, b) => (a < b ? 1 : -1))
    .map((name) => {
      const file = `data/snapshots/${name}`
      const ts = name.replace(/\.json$/, '')
      const age = ageMinutes(resolve(SNAPSHOTS_DIR, name)) ?? 0
      return { ts, file, markets: 0, diffsCount: 0, missingInfo: 0, freshMin: age }
    })
}

const STAGE_OUTPUTS: { id: string; label: string; cli: string; files: string[] }[] = [
  { id: 'context', label: 'Update context', cli: 'edit context/', files: [] },
  { id: 'packet', label: 'Build packet', cli: 'build-packet', files: ['packet.md', 'context_packet.md'] },
  {
    id: 'validate',
    label: 'Validate response',
    cli: 'validate-response',
    files: ['model_a_validation.txt', 'model_b_validation.txt', 'response_validation.txt']
  },
  {
    id: 'adj-in',
    label: 'Build adjudicator',
    cli: 'build-adjudicator-input',
    files: ['adjudicator_input.md']
  },
  {
    id: 'adj-val',
    label: 'Validate adjudicator',
    cli: 'validate-adjudicator',
    files: ['adjudicator_validation.txt']
  },
  { id: 'ticket', label: 'Build trade ticket', cli: 'build-trade-ticket', files: ['trade_ticket.md'] }
]

const newestAge = (files: string[], dir: string): number | null => {
  let youngest: number | null = null
  for (const f of files) {
    const a = ageMinutes(resolve(dir, f))
    if (a === null) continue
    if (youngest === null || a < youngest) youngest = a
  }
  return youngest
}

const fmtAgeTs = (age: number): string => {
  if (age < 60) return `${age}m ago`
  if (age < 1440) return `${Math.round(age / 60)}h ago`
  return `${Math.round(age / 1440)}d ago`
}

const readWorkflow = (freshness: FreshnessEntry[]): WorkflowStage[] => {
  const ctxStale = freshness.some((f) => f.state !== 'fresh')
  return STAGE_OUTPUTS.map(({ id, label, cli, files }) => {
    if (id === 'context') {
      const state: WorkflowState = ctxStale ? 'stale' : 'ok'
      const youngest = freshness.reduce<number | null>(
        (a, f) => (a === null || f.age < a ? f.age : a),
        null
      )
      return { id, label, cli, state, ts: youngest === null ? '—' : fmtAgeTs(youngest) }
    }
    if (files.length === 0) return { id, label, cli, state: 'pending' as WorkflowState, ts: '—' }
    const age = newestAge(files, REPORTS_DIR)
    if (age === null) return { id, label, cli, state: 'pending' as WorkflowState, ts: '—' }
    const state: WorkflowState = age < 1440 ? 'ok' : 'stale'
    return { id, label, cli, state, ts: fmtAgeTs(age) }
  })
}

export const readContext = (): PmDataPayload => {
  void REPO_ROOT
  const markets = applyPriceHistory(readMarkets())
  const positions = readPositions(markets)
  const openOrders = readOpenOrders(markets)
  const liveState = readLiveState()
  const freshness = readFreshness()
  const workflow = readWorkflow(freshness)
  const snapshots = readSnapshots()

  const positionsValue = positions.reduce((a, p) => a + p.shares * p.mark, 0)
  const equity = liveState.cash + positionsValue
  const totalPnl = positions.reduce((a, p) => a + (p.mark - p.avg) * p.shares, 0)
  const dayPnl = positions.reduce((a, p) => a + p.dayPnl, 0)

  return {
    markets,
    positions,
    openOrders,
    workflow,
    freshness,
    liveState,
    equity,
    dayPnl,
    totalPnl,
    heat: [],
    intake: [],
    snapshots,
    accountImport: readAccountImport()
  }
}
