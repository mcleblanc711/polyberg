import { describe, expect, it } from 'vitest'
import { domain, linePath, nearest, plotArea, scale, ticks } from './chart'

describe('research price chart geometry', () => {
  it('never produces negative plot dimensions', () => {
    expect(plotArea(10, 10)).toMatchObject({width: 0, height: 0})
    expect(plotArea(800, 260)).toMatchObject({width: 736, height: 218})
  })
  it('uses the full 0–100¢ range unless fitted, and clamps fitted ranges', () => {
    const series = [[{t: 1, p: 0.4}, {t: 2, p: 0.5}]]
    expect(domain(series, false)).toEqual({t0: 1, t1: 2, p0: 0, p1: 1})
    const fitted = domain(series, true)!
    expect(fitted.p0).toBeCloseTo(0.38)
    expect(fitted.p1).toBeCloseTo(0.52)
    expect(domain([[{t: 5, p: 0.995}]], true)).toMatchObject({t0: 5, t1: 6, p1: 1})
    expect(domain([[]], true)).toBeNull()
  })
  it('draws nothing for fewer than two points and maps prices top-down', () => {
    const s = scale({t0: 0, t1: 10, p0: 0, p1: 1}, {x: 0, y: 0, width: 100, height: 100})
    expect(linePath([{t: 0, p: 0.5}], s)).toBe('')
    expect(linePath([{t: 0, p: 1}, {t: 10, p: 0}], s)).toBe('M0.0 0.0 L100.0 100.0')
  })
  it('finds the nearest observation for the hover readout', () => {
    const points = [{t: 0, p: 0.1}, {t: 10, p: 0.2}, {t: 30, p: 0.3}]
    expect(nearest(points, 4)?.p).toBe(0.1)
    expect(nearest(points, 21)?.p).toBe(0.3)
    expect(nearest([], 1)).toBeNull()
    expect(ticks(0, 1, 3)).toEqual([0, 0.5, 1])
  })
})
