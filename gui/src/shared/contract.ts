export type Side = 'YES' | 'NO'
export type OrderKind = 'BUY' | 'SELL'
export type OrderStatus = 'WORKING' | 'FILLED' | 'CANCELLED'
export type RuleRisk = 'low' | 'medium' | 'high'
export type WorkflowState = 'ok' | 'stale' | 'pending'
export type FreshnessState = 'fresh' | 'aging' | 'stale'
export type IntakeKind = 'tweet' | 'article' | 'note'
export type IntakeStatus = 'suggested' | 'confirmed' | 'rejected'
export type Mode = 'RESEARCH' | 'TRADING' | 'PAUSED'

export interface Catalyst {
  t: string
  src: string
  txt: string
}

export interface PriceWindow {
  high: number
  low: number
}

export interface PriceWindows {
  d1: PriceWindow
  w1: PriceWindow
  m1: PriceWindow
}

export const EMPTY_PRICE_WINDOWS: PriceWindows = {
  d1: { high: 0, low: 0 },
  w1: { high: 0, low: 0 },
  m1: { high: 0, low: 0 }
}

// 'ok' = live book in live/order_books.json, 'unavailable' = fetch tried and
// failed (typically a resolved market), 'none' = not fetched / not flagged.
export type BookStatus = 'ok' | 'unavailable' | 'none'

export interface Market {
  id: string
  name: string
  url: string
  category: string
  ruleKey: string
  oracle: string
  preferredSide: Side
  resolutionDate: string
  expired: boolean
  ruleRisk: RuleRisk
  // mark/bid/ask/spread are quotes for preferredSide from live/order_books.json;
  // spread is in cents, liq is total resting notional on that side's book.
  bookStatus: BookStatus
  mark: number
  bid: number
  ask: number
  spread: number
  liq: number
  hist: number[]
  windows: PriceWindows
  windowsAsOf: string
  lastUpdate: string
  snapshotAge: number
  ruleText: string
  ruleRiskNotes: string[]
  catalysts: Catalyst[]
}

export interface Position {
  marketId: string
  side: Side
  shares: number
  avg: number
  mark: number
}

export interface OpenOrder {
  id: string
  marketId: string
  side: Side
  kind: OrderKind
  px: number
  qty: number
  status: OrderStatus
  placed: string
}

export interface WorkflowStage {
  id: string
  label: string
  state: WorkflowState
  ts: string
  cli: string
}

export interface FreshnessEntry {
  file: string
  age: number
  state: FreshnessState
}

export interface LiveState {
  mode: Mode
  cash: number
  thesis: string
  constraints: string[]
  notes: string
  proxyWallet: string
}

// One cell of the dashboard price tape: live preferred-side quote per market.
export interface HeatEntry {
  id: string
  px: number
  side: Side
  spread: number
}

export interface IntakeItem {
  id: string
  kind: IntakeKind
  addedAt: string
  author: string
  url: string
  text: string
  suggestedMarket: string | null
  suggestionConfidence: number
  status: IntakeStatus
}

export interface SnapshotMeta {
  ts: string
  file: string
  asOf: string
  markets: number
  missingInfo: number
  freshMin: number
  preview: string
}

export interface AccountImportFile {
  filename: string
  exists: boolean
  asOf: string
  source: string
  payloadJson: string
  canonicalText: string
  canonicalFilename: string
}

export interface AccountImport {
  positions: AccountImportFile
  balances: AccountImportFile
  openOrders: AccountImportFile
}

export interface PmDataPayload {
  markets: Market[]
  positions: Position[]
  openOrders: OpenOrder[]
  workflow: WorkflowStage[]
  freshness: FreshnessEntry[]
  liveState: LiveState
  equity: number
  totalPnl: number
  heat: HeatEntry[]
  intake: IntakeItem[]
  snapshots: SnapshotMeta[]
  accountImport: AccountImport
}

export interface RunStageResult {
  ok: boolean
  code: number
  stdout: string
  stderr: string
}

export interface DraftOrder {
  marketId: string
  side: Side
  kind: OrderKind
  price: number
  shares: number
  notes?: string
}

export type PasteKind = 'portfolio' | 'orders'

// Decision-leg JSON inputs pasted in the GUI: the two model responses fed to the
// adjudicator, and the adjudicator's own output. Written to reports/generated/decision/.
export type ResponseSlot = 'gpt' | 'claude' | 'adjudicator'

// JSON Schemas (in schemas/) the decision leg validates pasted responses against.
// Used to generate format-forcing prompts the user hands to Claude/GPT so their
// replies come back as schema-valid JSON.
export type SchemaName = 'model-trade-response' | 'adjudicator-output'

export const ALLOWED_STAGES = [
  'fetch-books',
  'build-packet',
  'packet',
  'validate-response',
  'validate-adjudicator',
  'build-adjudicator-input',
  'snapshot-markets',
  'diff-snapshots',
  'build-trade-ticket',
  'import-public-positions',
  'import-account-snapshot',
  'import-clob-orders',
  'import-clob-balance',
  'fetch-price-history',
  'promote-positions',
  'promote-orders',
  'promote-balance',
  'paste-import',
  'registry-add',
  'registry-update',
  'registry-delete',
  'ladder'
] as const

export type AllowedStage = (typeof ALLOWED_STAGES)[number]

export const isAllowedStage = (name: string): name is AllowedStage =>
  (ALLOWED_STAGES as readonly string[]).includes(name)

export const IPC = {
  readContext: 'pm:readContext',
  readArtifact: 'pm:readArtifact',
  readSchema: 'pm:readSchema',
  writeClipboard: 'pm:writeClipboard',
  openExternal: 'pm:openExternal',
  runStage: 'pm:runStage',
  runStageStream: 'pm:runStageStream',
  runStageStreamChunk: 'pm:runStageStream:chunk',
  appendCatalyst: 'pm:appendCatalyst',
  writeDraftOrder: 'pm:writeDraftOrder',
  writePasteInput: 'pm:writePasteInput',
  writeResponseInput: 'pm:writeResponseInput',
  watchStart: 'pm:watch:start',
  watchStop: 'pm:watch:stop',
  watchEvent: 'pm:watch:event'
} as const

export type ArtifactName =
  | 'packet'
  | 'adjudicator-input'
  | 'packet-gpt'
  | 'packet-claude'
  | 'trade-ticket'

export interface ArtifactRead {
  name: ArtifactName
  filename: string
  exists: boolean
  content: string
  bytes: number
  mtimeIso: string
  ageMin: number | null
}

export interface ContextChangeEvent {
  path: string
  kind: 'add' | 'change' | 'unlink'
}

export interface PmBridge {
  readContext: () => Promise<PmDataPayload>
  readArtifact: (name: ArtifactName) => Promise<ArtifactRead>
  readSchema: (name: SchemaName) => Promise<string>
  writeClipboard: (text: string) => Promise<void>
  openExternal: (url: string) => Promise<void>
  runStage: (name: string, args?: string[]) => Promise<RunStageResult>
  runStageStream: (
    name: string,
    args: string[],
    onChunk: (chunk: { stream: 'stdout' | 'stderr'; text: string }) => void
  ) => Promise<RunStageResult>
  appendCatalyst: (marketId: string, entry: Catalyst) => Promise<void>
  writeDraftOrder: (order: DraftOrder) => Promise<void>
  writePasteInput: (kind: PasteKind, text: string) => Promise<string>
  writeResponseInput: (slot: ResponseSlot, text: string) => Promise<string>
  onContextChange: (cb: (ev: ContextChangeEvent) => void) => () => void
}
