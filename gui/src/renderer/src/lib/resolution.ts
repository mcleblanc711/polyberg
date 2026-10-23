import type { MarketResolution } from './types'

// Visual weight of an oracle badge: 'open' = nothing to flag, 'pending' = a
// proposal is in its challenge window, 'disputed' = going to a vote,
// 'resolved' = printed on-chain.
export type OracleTone = 'open' | 'pending' | 'disputed' | 'resolved'

export interface OracleBadge {
  label: string
  tone: OracleTone
  title: string
}

const PENDING = new Set(['proposed', 'challenged', 'reproposed'])
const DISPUTED = new Set(['disputed', 'arbitration'])

// Map a market's live oracle state to the MarketsScreen badge. null when
// `resolution-status` has not produced a row for the market.
export const oracleBadge = (res: MarketResolution | null): OracleBadge | null => {
  if (!res) return null
  const settle = res.expectedSettlement ? ` · settles ~${res.expectedSettlement}` : ''
  const asOf = res.asOf ? ` (as of ${res.asOf})` : ''
  if (res.status === 'resolved') {
    const outcome = res.settledOutcome || '?'
    return {
      label: `RESOLVED ${outcome}`,
      tone: 'resolved',
      title: `oracle resolved ${outcome}${res.wasDisputed ? ' after a dispute' : ''}${asOf}`
    }
  }
  if (DISPUTED.has(res.status)) {
    return {
      label: 'DISPUTED',
      tone: 'disputed',
      title: `oracle ${res.status} — outcome goes to a vote${settle}${asOf}`
    }
  }
  if (PENDING.has(res.status)) {
    const proposed = res.proposedOutcome || '?'
    return {
      label: `PROPOSED ${proposed}`,
      tone: 'pending',
      title: `oracle ${res.status}, proposed ${proposed}${settle}${asOf}`
    }
  }
  return { label: 'OPEN', tone: 'open', title: `oracle ${res.status}${asOf}` }
}
