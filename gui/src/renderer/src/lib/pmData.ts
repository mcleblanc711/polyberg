import { isAllowedStage } from '../../../shared/contract'
import type { Market, MarketSuggestion, WorkflowStage } from './types'

const STOP_WORDS = new Set([
  'the', 'of', 'by', 'to', 'a', 'an', 'in', 'on', 'at', 'for', 'and', 'or', 'will',
  'be', 'between', 'any', 'day', 'how', 'many', 'market', 'this', 'that', 'with',
  'end', 'week', 'than', 'more', 'less'
])

const tokens = (s: string): string[] =>
  (s || '')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((w) => w.length >= 3 && !STOP_WORDS.has(w))

// Keyword-match pasted text against the live registry (id + name + category
// tokens), preferring unexpired markets. Replaces an older hardcoded keyword
// table whose market ids had all rotated out of the registry.
export const makeSuggestMarket = (markets: Market[]) => {
  const candidates = markets
    .filter((m) => !m.expired)
    .map((m) => ({
      id: m.id,
      words: new Set([
        ...tokens(m.id.replace(/_/g, ' ')),
        ...tokens(m.name),
        ...tokens(m.category.replace(/_/g, ' '))
      ])
    }))
  return (text: string): MarketSuggestion => {
    const words = [...new Set(tokens(text))]
    if (words.length === 0) return { id: null, confidence: 0 }
    let best = { id: null as string | null, score: 0 }
    for (const c of candidates) {
      const hits = words.filter((w) => c.words.has(w)).length
      if (hits > best.score) best = { id: c.id, score: hits }
    }
    if (!best.id || best.score < 2) return { id: null, confidence: 0 }
    return { id: best.id, confidence: Math.min(0.95, 0.3 + best.score * 0.15) }
  }
}

export const makeMarketById = (markets: Market[]) => {
  const idx = new Map(markets.map((m) => [m.id, m]))
  return (id: string): Market | undefined => idx.get(id)
}

// The first workflow stage that is stale/pending and runnable from the GUI —
// what "RUN NEXT STAGE" will actually execute.
export const nextRunnableStage = (workflow: WorkflowStage[]): WorkflowStage | null =>
  workflow.find((w) => w.state !== 'ok' && isAllowedStage(w.cli)) ?? null
