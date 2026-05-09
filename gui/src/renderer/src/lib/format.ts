export const fmtUsd = (n: number, signed = false): string => {
  const sign = signed && n > 0 ? '+' : ''
  const body = (n < 0 ? '-' : '') + '$' + Math.abs(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return sign + body
}

export const fmtPct = (n: number, signed = false): string =>
  (signed && n > 0 ? '+' : '') + n.toFixed(2) + '%'

export const fmtCents = (n: number): string => (n * 100).toFixed(1) + '¢'
