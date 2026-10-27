// Pure geometry for the research price chart. Dimensions are clamped so a small or
// collapsed container can never produce negative SVG widths.
export interface Point { t: number; p: number }
export interface Area { x: number; y: number; width: number; height: number }
export interface Domain { t0: number; t1: number; p0: number; p1: number }

export const PAD = {left: 48, right: 16, top: 14, bottom: 28}

export function plotArea(width: number, height: number): Area {
  return {x: PAD.left, y: PAD.top, width: Math.max(0, width - PAD.left - PAD.right), height: Math.max(0, height - PAD.top - PAD.bottom)}
}

export function domain(series: Point[][], fit: boolean): Domain | null {
  const points = series.flat()
  if (points.length === 0) return null
  const ts = points.map(x => x.t)
  let t0 = Math.min(...ts), t1 = Math.max(...ts)
  if (t1 === t0) t1 = t0 + 1
  if (!fit) return {t0, t1, p0: 0, p1: 1}
  const ps = points.map(x => x.p)
  const span = Math.max(...ps) - Math.min(...ps)
  const margin = Math.max(span * 0.1, 0.02)
  return {t0, t1, p0: Math.max(0, Math.min(...ps) - margin), p1: Math.min(1, Math.max(...ps) + margin)}
}

export function scale(d: Domain, area: Area): {x: (t: number) => number; y: (p: number) => number} {
  const dp = d.p1 - d.p0 || 1
  return {
    x: t => area.x + ((t - d.t0) / (d.t1 - d.t0)) * area.width,
    y: p => area.y + area.height - ((p - d.p0) / dp) * area.height
  }
}

export function linePath(points: Point[], s: ReturnType<typeof scale>): string {
  if (points.length < 2) return ''
  return points.map((pt, i) => `${i ? 'L' : 'M'}${s.x(pt.t).toFixed(1)} ${s.y(pt.p).toFixed(1)}`).join(' ')
}

// Points are sorted by time; returns the observation closest to t.
export function nearest<T extends Point>(points: T[], t: number): T | null {
  if (points.length === 0) return null
  let lo = 0, hi = points.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (points[mid].t < t) lo = mid; else hi = mid
  }
  return Math.abs(points[lo].t - t) <= Math.abs(points[hi].t - t) ? points[lo] : points[hi]
}

export function ticks(lo: number, hi: number, count: number): number[] {
  if (count < 2 || hi <= lo) return [lo]
  return Array.from({length: count}, (_, i) => lo + ((hi - lo) * i) / (count - 1))
}

export function timeLabel(seconds: number, span: string): string {
  const at = new Date(seconds * 1000)
  if (span === '1d') return at.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
  if (span === 'max') return at.toLocaleDateString([], {month: 'short', year: '2-digit'})
  return at.toLocaleDateString([], {month: 'short', day: 'numeric'})
}
