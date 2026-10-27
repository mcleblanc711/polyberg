import type { ReactNode } from 'react'

export const when = (at: string | null): string => at ? new Date(at).toLocaleString() : 'Unavailable'
export const px = (value: number | null | undefined): string => value == null ? '—' : `${(value * 100).toFixed(1)}¢`
export const signedPx = (value: number | null | undefined): string => value == null ? '—' : `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value * 100).toFixed(1)}¢`
const compact = new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1})
export const usd = (value: number | null | undefined): string => value == null ? 'Unavailable' : compact.format(value)
export const shares = (value: number): string => value.toLocaleString('en-US', {maximumFractionDigits: 2})
export const attempt = (work: () => Promise<unknown>): void => { void work().catch(() => undefined) }
export function SourceLink({url, children}: {url: string; children?: ReactNode}): JSX.Element {
  return <button className="research-link" onClick={() => attempt(() => window.pm.openExternal(url))}>{children || url}</button>
}
