import { describe, expect, it } from 'vitest'
import { flagEmoji, geoChip } from './geo'

describe('flagEmoji', () => {
  it('maps a two-letter country code to its regional-indicator flag', () => {
    expect(flagEmoji('CA')).toBe('🇨🇦')
  })

  it('returns empty for anything that is not two capital letters', () => {
    expect(flagEmoji('')).toBe('')
    expect(flagEmoji('ca')).toBe('')
    expect(flagEmoji('CAN')).toBe('')
  })
})

describe('geoChip', () => {
  it('is unknown until geo-check has run', () => {
    expect(geoChip(null)).toMatchObject({ text: 'GEO ?', tone: 'unknown' })
  })

  it('shows the Canadian province code, names it in the tooltip, and flags a block', () => {
    const chip = geoChip({ blocked: true, country: 'CA', region: 'AB', asOf: '2026-10-23T07:41:14-06:00' })
    expect(chip.text).toBe('🇨🇦 CA-AB BLOCKED')
    expect(chip.tone).toBe('blocked')
    expect(chip.title).toContain('CA / AB (Alberta)')
    expect(chip.title).toContain('orders from this IP are rejected')
  })

  it('shows an allowed Canadian province as OK', () => {
    expect(geoChip({ blocked: false, country: 'CA', region: 'SK', asOf: '' })).toMatchObject({
      text: '🇨🇦 CA-SK OK',
      tone: 'allowed'
    })
  })

  it('keeps an unknown Canadian region code without inventing a name', () => {
    const chip = geoChip({ blocked: false, country: 'CA', region: 'ZZ', asOf: '' })
    expect(chip.text).toBe('🇨🇦 CA-ZZ OK')
    expect(chip.title).toContain('CA / ZZ (not blocked)')
  })

  it('shows only the country outside Canada', () => {
    expect(geoChip({ blocked: true, country: 'GB', region: 'ENG', asOf: '' }).text).toBe(
      '🇬🇧 GB BLOCKED'
    )
  })
})
