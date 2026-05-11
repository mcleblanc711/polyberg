export type {
  Side,
  OrderKind,
  OrderStatus,
  RuleRisk,
  WorkflowState,
  FreshnessState,
  IntakeKind,
  IntakeStatus,
  Mode,
  Catalyst,
  Market,
  Position,
  OpenOrder,
  WorkflowStage,
  FreshnessEntry,
  LiveState,
  HeatEntry,
  IntakeItem,
  SnapshotMeta,
  PmDataPayload,
  AccountImport,
  AccountImportFile
} from '../../../shared/contract'

import type { PmDataPayload } from '../../../shared/contract'

export interface MarketSuggestion {
  id: string | null
  confidence: number
}

export interface PmData extends PmDataPayload {
  fmtUsd: (n: number, signed?: boolean) => string
  fmtPct: (n: number, signed?: boolean) => string
  fmtCents: (n: number) => string
  suggestMarket: (text: string) => MarketSuggestion
  marketById: (id: string) => PmDataPayload['markets'][number] | undefined
}
