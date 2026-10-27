import { useState, type MouseEvent } from 'react'
import type { ResearchPriceSeries } from '../../../shared/research'
import { domain, linePath, nearest, plotArea, scale, ticks, timeLabel } from './chart'
import { px } from './common'

export const SERIES_COLORS = ['#00ffd1', '#ff3df0', '#ffb420', '#5cf3d3', '#ff3d6b', '#f0e8f5']
export interface ChartLine { series: ResearchPriceSeries; color: string }
const W = 800, H = 260

// Hand-rolled SVG so research never imports the legacy dashboard charts.
export function PriceHistoryChart({lines, span, fit}: {lines: ChartLine[]; span: string; fit: boolean}): JSX.Element {
  const [hoverT, setHoverT] = useState<number | null>(null)
  const area = plotArea(W, H)
  const d = domain(lines.map(l => l.series.points), fit)
  if (!d || lines.every(l => l.series.points.length < 2)) return <div className="research-chart-empty">Not enough public price history for this span.</div>
  const s = scale(d, area)
  const move = (e: MouseEvent<SVGRectElement>): void => {
    const box = e.currentTarget.ownerSVGElement?.getBoundingClientRect()
    if (!box || box.width === 0) return
    const x = ((e.clientX - box.left) / box.width) * W
    setHoverT(d.t0 + ((x - area.x) / Math.max(1, area.width)) * (d.t1 - d.t0))
  }
  const readout = hoverT == null ? [] : lines.map(l => ({label: l.series.label, color: l.color, point: nearest(l.series.points, hoverT)}))
  const at = readout.find(r => r.point)?.point?.t
  return <div className="research-chart">
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Outcome price history">
      {ticks(d.p0, d.p1, 5).map(p => <g key={`p${p}`}><line x1={area.x} x2={area.x + area.width} y1={s.y(p)} y2={s.y(p)} className="grid" /><text x={area.x - 8} y={s.y(p) + 4} textAnchor="end">{px(p)}</text></g>)}
      {ticks(d.t0, d.t1, 5).map((t, i) => <text key={`t${i}`} x={s.x(t)} y={H - 8} textAnchor={i === 0 ? 'start' : i === 4 ? 'end' : 'middle'}>{timeLabel(t, span)}</text>)}
      {lines.map(l => <path key={l.series.outcome_id} d={linePath(l.series.points, s)} fill="none" stroke={l.color} strokeWidth={1.6} />)}
      {at != null && <line x1={s.x(at)} x2={s.x(at)} y1={area.y} y2={area.y + area.height} className="crosshair" />}
      {readout.map(r => r.point && <circle key={r.label} cx={s.x(r.point.t)} cy={s.y(r.point.p)} r={3} fill={r.color} />)}
      <rect x={area.x} y={area.y} width={area.width} height={area.height} fill="transparent" onMouseMove={move} onMouseLeave={() => setHoverT(null)} />
    </svg>
    <div className="research-chart-readout" aria-live="polite">{at != null
      ? <>{new Date(at * 1000).toLocaleString()}{readout.map(r => r.point && <span key={r.label} style={{color: r.color}}>{r.label} {px(r.point.p)}</span>)}</>
      : <span className="muted">Hover the chart for exact prices.</span>}</div>
  </div>
}
