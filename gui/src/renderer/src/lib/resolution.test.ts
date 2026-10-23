import { describe, expect, it } from 'vitest'
import { oracleBadge } from './resolution'
import type { MarketResolution } from './types'

const res = (overrides: Partial<MarketResolution>): MarketResolution => ({
  status: 'posed',
  wasDisputed: false,
  proposedOutcome: '',
  settledOutcome: '',
  expectedSettlement: '',
  suggestedLifecycle: '',
  asOf: '',
  ...overrides
})

describe('oracleBadge', () => {
  it('is null until resolution-status has a row', () => {
    expect(oracleBadge(null)).toBeNull()
  })

  it('shows an open oracle as OPEN', () => {
    expect(oracleBadge(res({ status: 'posed' }))).toMatchObject({ label: 'OPEN', tone: 'open' })
  })

  it('shows the proposed outcome and settlement estimate while a proposal is live', () => {
    const badge = oracleBadge(
      res({ status: 'challenged', proposedOutcome: 'NO', expectedSettlement: '2026-10-24T12:00:00Z' })
    )
    expect(badge).toMatchObject({ label: 'PROPOSED NO', tone: 'pending' })
    expect(badge?.title).toContain('settles ~2026-10-24T12:00:00Z')
  })

  it('flags disputes and arbitration as DISPUTED', () => {
    expect(oracleBadge(res({ status: 'disputed' }))?.tone).toBe('disputed')
    expect(oracleBadge(res({ status: 'arbitration' }))?.label).toBe('DISPUTED')
  })

  it('shows the settled outcome and notes a prior dispute', () => {
    const badge = oracleBadge(res({ status: 'resolved', settledOutcome: 'YES', wasDisputed: true }))
    expect(badge).toMatchObject({ label: 'RESOLVED YES', tone: 'resolved' })
    expect(badge?.title).toContain('after a dispute')
  })

  it('falls back to ? when an outcome is missing', () => {
    expect(oracleBadge(res({ status: 'resolved' }))?.label).toBe('RESOLVED ?')
    expect(oracleBadge(res({ status: 'proposed' }))?.label).toBe('PROPOSED ?')
  })
})
