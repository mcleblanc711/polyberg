import type { Market, MarketSuggestion } from './types'

const tagRules: { id: string; kw: string[] }[] = [
  { id: 'hormuz_normal_may15', kw: ['hormuz', 'strait', 'soh', 'irgcn', 'larak', 'tanker', 'vlcc'] },
  { id: 'cl_high_120_end_june', kw: ['brent', 'crude', 'wti', 'iea', 'eia', 'opec', 'petrochem', 'demand'] },
  {
    id: 'trump_blockade_lifted_apr30',
    kw: ['advisory', 'state dept', 'state department', 'blockade', 'gulf advisory', 'rescind', 'downgrade']
  }
]

export const makeSuggestMarket = (markets: Market[]) => {
  const known = new Set(markets.map((m) => m.id))
  return (text: string): MarketSuggestion => {
    const t = (text || '').toLowerCase()
    let best = { id: null as string | null, score: 0 }
    for (const r of tagRules) {
      if (!known.has(r.id)) continue
      const hits = r.kw.filter((k) => t.includes(k)).length
      if (hits > best.score) best = { id: r.id, score: hits }
    }
    if (!best.id) return { id: null, confidence: 0 }
    return { id: best.id, confidence: Math.min(0.95, 0.4 + best.score * 0.18) }
  }
}

export const makeMarketById = (markets: Market[]) => {
  const idx = new Map(markets.map((m) => [m.id, m]))
  return (id: string): Market | undefined => idx.get(id)
}
