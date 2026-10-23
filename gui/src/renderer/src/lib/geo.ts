import type { GeoStatus } from './types'

const CA_PROVINCES: Record<string, string> = {
  AB: 'Alberta',
  BC: 'British Columbia',
  MB: 'Manitoba',
  NB: 'New Brunswick',
  NL: 'Newfoundland and Labrador',
  NS: 'Nova Scotia',
  NT: 'Northwest Territories',
  NU: 'Nunavut',
  ON: 'Ontario',
  PE: 'Prince Edward Island',
  QC: 'Quebec',
  SK: 'Saskatchewan',
  YT: 'Yukon'
}

// Regional-indicator flag emoji for an ISO 3166-1 alpha-2 code; '' otherwise.
export const flagEmoji = (country: string): string =>
  /^[A-Z]{2}$/.test(country)
    ? String.fromCodePoint(...[...country].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
    : ''

export type GeoTone = 'blocked' | 'allowed' | 'unknown'

export interface GeoChip {
  text: string
  tone: GeoTone
  title: string
}

// TopBar flag for Polymarket's geoblock verdict. Canada shows its province
// code (CA-AB) because Polymarket restricts by province; the full name is in
// the tooltip so the chip stays narrow enough for the crowded TopBar.
export const geoChip = (geo: GeoStatus | null): GeoChip => {
  if (!geo) {
    return {
      text: 'GEO ?',
      tone: 'unknown',
      title: 'Polymarket geoblock not checked yet. Click to run geo-check.'
    }
  }
  const country = geo.country || '??'
  const isCanada = geo.country === 'CA' && geo.region !== ''
  const place = isCanada ? `${country}-${geo.region}` : country
  const provinceName = isCanada ? CA_PROVINCES[geo.region] : undefined
  const flag = flagEmoji(geo.country)
  const verdict = geo.blocked ? 'BLOCKED' : 'OK'
  const codes = [geo.country, geo.region].filter(Boolean).join(' / ')
  const where = codes ? codes + (provinceName ? ` (${provinceName})` : '') : 'unknown location'
  return {
    text: `${flag ? `${flag} ` : ''}${place} ${verdict}`,
    tone: geo.blocked ? 'blocked' : 'allowed',
    title:
      `Polymarket geoblock for this machine's public IP: ${where}` +
      (geo.blocked ? ' (orders from this IP are rejected)' : ' (not blocked)') +
      (geo.asOf ? `. Checked ${geo.asOf}` : '') +
      '. Click to re-check.'
  }
}
