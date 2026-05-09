export type Side = 'YES' | 'NO'
export type OrderKind = 'BUY' | 'SELL'
export type OrderStatus = 'WORKING' | 'FILLED' | 'CANCELLED'
export type RuleRisk = 'low' | 'medium' | 'high'
export type WorkflowState = 'ok' | 'stale' | 'pending'
export type FreshnessState = 'fresh' | 'aging' | 'stale'
export type IntakeKind = 'tweet' | 'article' | 'note'
export type IntakeStatus = 'suggested' | 'confirmed' | 'rejected'
export type Mode = 'RESEARCH' | 'TRADING' | 'PAUSED'
export type Lean = 'YES' | 'NO' | null

export interface Catalyst {
  t: string
  src: string
  txt: string
}

export interface Market {
  id: string
  name: string
  url: string
  category: string
  ruleKey: string
  oracle: string
  preferredSide: Side
  resolutionDate: string
  ruleRisk: RuleRisk
  mark: number
  bid: number
  ask: number
  spread: number
  liq: number
  hist: number[]
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
  dayPnl: number
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
}

export interface HeatEntry {
  id: string
  d: number
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
  markets: number
  diffsCount: number
  missingInfo: number
  freshMin: number
}

export interface SentimentEntry {
  score: number | null
  n: number
  lean: Lean
}

export interface Sentiment {
  enabled: boolean
  source: string
  asOf: string | null
  perMarket: Record<string, SentimentEntry>
}

export interface MarketSuggestion {
  id: string | null
  confidence: number
}

export interface PmData {
  markets: Market[]
  positions: Position[]
  openOrders: OpenOrder[]
  workflow: WorkflowStage[]
  freshness: FreshnessEntry[]
  liveState: LiveState
  equity: number
  dayPnl: number
  totalPnl: number
  heat: HeatEntry[]
  intake: IntakeItem[]
  snapshots: SnapshotMeta[]
  sentiment: Sentiment
  fmtUsd: (n: number, signed?: boolean) => string
  fmtPct: (n: number, signed?: boolean) => string
  fmtCents: (n: number) => string
  suggestMarket: (text: string) => MarketSuggestion
  marketById: (id: string) => Market | undefined
}
