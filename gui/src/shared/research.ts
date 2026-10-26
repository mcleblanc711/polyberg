export const RESEARCH_OPERATIONS = [
  'init', 'search', 'inspect', 'follow', 'list', 'show', 'refresh', 'unfollow', 'refollow',
  'status', 'tags', 'archive', 'unarchive', 'projects', 'project_create', 'project_add',
  'project_remove', 'note', 'verify', 'rules', 'annotate', 'relate', 'compare', 'history',
  'packet', 'render'
] as const
export const RESEARCH_IPC = {
  request: 'research:request', watchStart: 'research:watch:start', watchStop: 'research:watch:stop',
  changed: 'research:changed', workspace: 'workspace:select'
} as const
export const STATUSES = ['discovered', 'screening', 'researching', 'monitoring', 'rejected', 'archived'] as const
export const CATEGORIES = ['observation', 'evidence_summary', 'question', 'catalyst', 'hypothesis', 'scenario', 'contradiction', 'model_interpretation'] as const
export const RELATIONSHIPS = ['related', 'same_topic', 'correlated', 'mutually_exclusive', 'exhaustive', 'complementary', 'overlapping', 'alternative_deadline', 'same_measurement', 'implication', 'causal', 'prerequisite'] as const
export const ANNOTATIONS = ['conditions', 'oracle', 'resolution_source', 'fallback', 'ambiguity', 'dispute', 'measurement_period', 'resolution_deadline'] as const
export interface ResearchSource { url: string; title?: string; published_at?: string | null; observed_at?: string | null }
export interface ResearchRequest {
  operation: typeof RESEARCH_OPERATIONS[number]
  reference?: string; market?: string; event?: string; project?: string
  all_markets?: boolean; include_closed?: boolean; status?: string; tags?: string[]
  category?: string; text?: string; sources?: ResearchSource[]; entry_id?: number
  version_id?: number; kind?: string; source_url?: string; other_market?: string; packet_id?: string
}
export interface ResearchOutcome {
  outcome_id: string; index: number; label: string; token_id: string | null
  position_id: string | null; asset_id: string | null
}
export interface ResearchIdentity {
  market_id: string; event_id: string | null; slug: string | null; question: string
  condition_id: string | null; question_id: string | null; protocol: string | null
  lifecycle: string; trading_start: string | null; trading_end: string | null
  page_url: string | null; api_url: string; outcomes: ResearchOutcome[]
}
export interface ResearchQuote {
  outcome_id: string; displayed_price: number | null; displayed_at: string | null
  best_bid: number | null; best_ask: number | null; midpoint: number | null; last_trade: number | null
  book_retrieved_at: string | null; midpoint_retrieved_at: string | null
  last_trade_retrieved_at: string | null; book_timestamp: string | null
  source_urls: string[]; warnings: string[]
}
export interface RulesAnnotation {
  annotation_id: number; kind: string; text: string; source_url: string
  created_at: string; rules_version_id: number; needs_review: boolean
}
export interface ResearchRules {
  text: string; text_sha256: string; api_url: string; page_url: string | null
  resolution_source: string | null; resolution_status: string | null
  rules_version_id: number; first_retrieved_at: string; observations: string[]; annotations: RulesAnnotation[]
}
export interface ResearchEntry {
  entry_id: number; category: string; text: string; created_at: string
  verified_at: string | null; sources: ResearchSource[]
}
export interface ResearchRelationship {
  relationship_id: number; from_market: string; to_market: string; kind: string
  explanation: string; source_url: string | null; created_at: string
}
export interface ResearchMarket {
  identification: ResearchIdentity; status: string; followed: boolean; tags: string[]; projects: string[]
  snapshot: { snapshot_id: number; retrieved_at: string; rules_version_id: number | null; quotes: ResearchQuote[]; warnings: string[] } | null
  rules: ResearchRules | null; entries: ResearchEntry[]; relationships: ResearchRelationship[]
  last_attempt_at: string | null; last_success_at: string | null; warnings: string[]
}
export interface ResearchList { markets: ResearchMarket[]; projects: { name: string; created_at: string }[] }
export interface ResearchDiscovery {
  events: {event_id: string; title: string; expected_market_ids: string[]}[]
  markets: {identification: ResearchIdentity; warnings: string[]}[]; warnings: string[]
}
export interface ResearchPacketResult {
  packet_id: string; snapshot_sha256: string
  packet: { markets: ResearchMarket[]; warnings: string[]; generated_at: string }
  contents: Record<'canonical.json' | 'shared.md' | 'gpt.md' | 'claude.md', string>
  export?: { directory: string }
}
export interface ResearchBridge {
  request: <T = Record<string, unknown>>(request: ResearchRequest) => Promise<T>
  selectWorkspace: (workspace: 'research' | 'legacy') => Promise<void>
  onChange: (cb: () => void) => () => void
}

// Validate before spawning; Python independently rejects unknown operations and fields.
export function validateResearchRequest(value: unknown): ResearchRequest {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid research request')
  const v = value as Record<string, unknown>
  const strings = ['reference', 'market', 'event', 'project', 'status', 'category', 'text', 'kind', 'source_url', 'other_market', 'packet_id']
  const keys = new Set(['operation', ...strings, 'all_markets', 'include_closed', 'tags', 'sources', 'entry_id', 'version_id'])
  if (Object.keys(v).some(k => !keys.has(k)) || !RESEARCH_OPERATIONS.includes(v.operation as never)) throw new Error('Invalid research operation or field')
  for (const key of strings) if (v[key] !== undefined && (typeof v[key] !== 'string' || (v[key] as string).length > 200000)) throw new Error('Invalid research string')
  for (const key of ['all_markets', 'include_closed']) if (v[key] !== undefined && typeof v[key] !== 'boolean') throw new Error('Invalid research flag')
  for (const key of ['entry_id', 'version_id']) if (v[key] !== undefined && (!Number.isSafeInteger(v[key]) || (v[key] as number) < 1)) throw new Error('Invalid research ID')
  if (v.tags !== undefined && (!Array.isArray(v.tags) || v.tags.some(t => typeof t !== 'string'))) throw new Error('Invalid research tags')
  if (v.sources !== undefined) {
    if (!Array.isArray(v.sources)) throw new Error('Invalid research sources')
    for (const source of v.sources) {
      if (!source || typeof source !== 'object' || Array.isArray(source) || typeof source.url !== 'string') throw new Error('Invalid source')
      if (Object.keys(source).some(k => !['url', 'title', 'published_at', 'observed_at'].includes(k))) throw new Error('Invalid source field')
      if (Object.values(source).some(x => x !== null && typeof x !== 'string')) throw new Error('Invalid source value')
      const url = new URL(source.url)
      if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Invalid source URL')
    }
  }
  if (new TextEncoder().encode(JSON.stringify(v)).length > 2000000) throw new Error('Research request too large')
  return v as unknown as ResearchRequest
}
