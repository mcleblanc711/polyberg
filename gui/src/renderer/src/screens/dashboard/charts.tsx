import { useId, type CSSProperties } from 'react'
import { fmtUsd } from '../../lib/format'
import type { Market, Position } from '../../lib/types'
import { colors as C, fonts as F } from '../../styles/tokens'

const ChartPlaceholder = ({ w, h, hint }: { w: number; h: number; hint: string }) => (
  <div
    style={{
      width: w,
      height: h,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      border: `1px dashed ${C.line}`,
      color: C.textMute,
      fontFamily: F.mono,
      fontSize: 9.5,
      letterSpacing: 0.4,
      textAlign: 'center',
      boxSizing: 'border-box'
    }}
  >
    {hint}
  </div>
)

export const Spark = ({
  data,
  w = 120,
  h = 32,
  color = C.cyan
}: {
  data: number[]
  w?: number
  h?: number
  color?: string
}) => {
  const gradId = useId()
  if (data.length < 2) return <ChartPlaceholder w={w} h={h} hint="no history" />
  const max = Math.max(...data)
  const min = Math.min(...data)
  const dx = w / (data.length - 1)
  const y = (v: number) => h - ((v - min) / (max - min || 1)) * (h - 4) - 2
  const path = data.map((v, i) => `${i ? 'L' : 'M'}${(i * dx).toFixed(1)},${y(v).toFixed(1)}`).join('')
  const fill = `${path}L${w},${h}L0,${h}Z`
  const style: CSSProperties = { display: 'block', filter: `drop-shadow(0 0 3px ${color}88)` }
  return (
    <svg width={w} height={h} style={style}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.4" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={fill} fill={`url(#${gradId})`} />
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  )
}

export const PriceChart = ({ data, w, h }: { data: number[]; w: number; h: number }) => {
  const fillId = useId()
  const gridId = useId()
  if (data.length < 2)
    return <ChartPlaceholder w={w} h={h} hint="no price history — $ fetch-price-history" />
  const pad = { l: 36, r: 14, t: 16, b: 24 }
  const iw = w - pad.l - pad.r
  const ih = h - pad.t - pad.b
  const max = Math.max(...data)
  const min = Math.min(...data)
  const dx = iw / (data.length - 1)
  const y = (v: number) => pad.t + ih - ((v - min) / (max - min || 1)) * ih
  const path = data.map((v, i) => `${i ? 'L' : 'M'}${(pad.l + i * dx).toFixed(1)},${y(v).toFixed(1)}`).join('')
  const fill = `${path}L${(pad.l + (data.length - 1) * dx).toFixed(1)},${pad.t + ih}L${pad.l},${pad.t + ih}Z`
  const ticks = [min, (min + max) / 2, max]
  const last = data[data.length - 1]!
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <defs>
        <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={C.magenta} stopOpacity="0.32" />
          <stop offset="100%" stopColor={C.magenta} stopOpacity="0" />
        </linearGradient>
        <pattern id={gridId} width={iw / 6} height={ih / 4} patternUnits="userSpaceOnUse">
          <path d={`M ${iw / 6} 0 L 0 0 0 ${ih / 4}`} fill="none" stroke={C.line2} strokeWidth={0.5} />
        </pattern>
      </defs>
      <rect x={pad.l} y={pad.t} width={iw} height={ih} fill={`url(#${gridId})`} />
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} stroke={C.line} strokeDasharray="2 6" />
          <text
            x={pad.l - 8}
            y={y(t) + 3}
            textAnchor="end"
            fill={C.textMute}
            fontSize="10"
            fontFamily={F.mono}
          >
            {(t * 100).toFixed(0)}¢
          </text>
        </g>
      ))}
      <path d={fill} fill={`url(#${fillId})`} />
      <path
        d={path}
        fill="none"
        stroke={C.magenta}
        strokeWidth={2}
        strokeLinejoin="round"
        style={{ filter: `drop-shadow(0 0 4px ${C.magenta}99)` }}
      />
      <circle cx={pad.l + (data.length - 1) * dx} cy={y(last)} r={4} fill={C.magenta} />
      <circle cx={pad.l + (data.length - 1) * dx} cy={y(last)} r={9} fill={C.magenta} opacity={0.25} />
    </svg>
  )
}

export const Treemap = ({
  positions,
  marketById,
  w,
  h
}: {
  positions: Position[]
  marketById: (id: string) => Market | undefined
  w: number
  h: number
}) => {
  const items = positions
    .map((p) => {
      const m = marketById(p.marketId)
      if (!m) return null
      return { ...p, m, notional: p.shares * p.mark, pnl: (p.mark - p.avg) * p.shares }
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)
  const total = items.reduce((a, i) => a + i.notional, 0) || 1
  let x = 0
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      {items.map((it, i) => {
        const cw = (it.notional / total) * w
        const accent = it.pnl >= 0 ? C.cyan : C.red
        const fill = it.pnl >= 0 ? 'rgba(0,255,209,0.10)' : 'rgba(255,61,107,0.10)'
        const node = (
          <g key={i} transform={`translate(${x},0)`}>
            <rect width={cw - 3} height={h} fill={fill} stroke={accent} strokeOpacity={0.5} />
            <text x={10} y={18} fill={C.text} fontSize="11" fontWeight="600" fontFamily={F.display} letterSpacing="0.5">
              {it.m.id.split('_')[0]!.toUpperCase()}
            </text>
            <text x={10} y={32} fill={C.textDim} fontSize="9.5" fontFamily={F.mono} letterSpacing="0.4">
              {it.side} · {it.shares}
            </text>
            <text x={10} y={h - 22} fill={accent} fontSize="13" fontFamily={F.mono} fontWeight="700">
              {fmtUsd(it.pnl, true)}
            </text>
            <text x={10} y={h - 8} fill={C.textMute} fontSize="9.5" fontFamily={F.mono}>
              {((it.notional / total) * 100).toFixed(0)}% · {fmtUsd(it.notional)}
            </text>
          </g>
        )
        x += cw
        return node
      })}
    </svg>
  )
}
