import { describe, expect, it } from 'vitest'
import { validateResearchRequest } from './research'

describe('research operation boundary', () => {
  it('accepts structured public requests and source provenance', () => {
    expect(validateResearchRequest({operation: 'follow', reference: 'https://polymarket.com/event/synthetic'}).operation).toBe('follow')
    expect(validateResearchRequest({operation: 'note', market: '900001', category: 'observation', text: 'Synthetic observation', sources: [{url: 'https://example.invalid/source', published_at: '2026-10-26T12:00:00Z'}]}).sources).toHaveLength(1)
  })
  it('accepts market-viewer reads with an allowlisted span', () => {
    expect(validateResearchRequest({operation: 'price_history', market: '900001', span: 'max', refetch: true}).span).toBe('max')
    expect(validateResearchRequest({operation: 'book', market: '900001'}).operation).toBe('book')
  })
  it.each([
    {operation: 'legacy'}, {operation: 'runStage', name: 'ladder'},
    {operation: 'list', wallet: 'SYNTHETIC_SECRET'}, {operation: 'list', db: '/legacy/account.json'},
    {operation: 'packet', output_dir: '/legacy'}, {operation: 'note', sources: [{url: 'file:///legacy'}]},
    {operation: 'note', sources: [{url: 'https://example.invalid', owner: 'SYNTHETIC_SECRET'}]},
    {operation: 'status', market: ['900001']}, {operation: 'verify', entry_id: '1'},
    {operation: 'list', all_markets: 1}, {operation: 'tags', tags: [42]},
    {operation: 'price_history', market: '900001', span: '2y'},
    {operation: 'price_history', market: '900001', span: 7},
    {operation: 'price_history', market: '900001', refetch: 'yes'},
    {operation: 'book', market: '900001', depth: 500}
  ])('rejects unsupported operations, fields, and types: %j', request => {
    expect(() => validateResearchRequest(request)).toThrow()
  })
})
