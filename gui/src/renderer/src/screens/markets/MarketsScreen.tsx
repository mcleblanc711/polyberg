import type { CSSProperties } from 'react'
import { usePmData } from '../../lib/pmDataContext'
import { colors as C, fonts as F } from '../../styles/tokens'
import type { RuleRisk } from '../../lib/types'

const riskColor = (risk: RuleRisk): string =>
  risk === 'high' ? C.red : risk === 'medium' ? C.amber : C.textDim

const riskBorder = (risk: RuleRisk): string =>
  risk === 'high' ? C.red : risk === 'medium' ? C.amber : C.line

export const MarketsScreen = () => {
  const pmData = usePmData()
  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.h1}>MARKET REGISTRY</div>
          <div style={S.h1Sub}>
            // market_registry.yaml · {pmData.markets.length} tracked · read/write
          </div>
        </div>
        <button style={S.btnGhost}>+ ADD MARKET</button>
      </div>
      <div style={S.panel}>
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>MARKET ID</th>
              <th style={S.th}>NAME</th>
              <th style={S.th}>RULE-KEY</th>
              <th style={S.th}>ORACLE</th>
              <th style={S.th}>RESOLVES</th>
              <th style={S.th}>RULE-RISK</th>
              <th style={S.th}>MARK</th>
              <th style={S.th} />
            </tr>
          </thead>
          <tbody>
            {pmData.markets.map((m) => (
              <tr key={m.id}>
                <td style={{ ...S.td, color: C.magenta, fontWeight: 700 }}>{m.id}</td>
                <td style={{ ...S.td, fontFamily: F.body, maxWidth: 320 }}>{m.name}</td>
                <td style={S.td}>{m.ruleKey}</td>
                <td style={S.td}>{m.oracle}</td>
                <td style={S.td}>{m.resolutionDate.split('T')[0]}</td>
                <td style={S.td}>
                  <span
                    style={{
                      ...S.chip,
                      color: riskColor(m.ruleRisk),
                      borderColor: riskBorder(m.ruleRisk)
                    }}
                  >
                    {m.ruleRisk}
                  </span>
                </td>
                <td style={{ ...S.td, color: C.cyan }}>
                  {m.mark > 0 ? `${(m.mark * 100).toFixed(1)}¢` : '—'}
                </td>
                <td style={S.td}>
                  <button style={{ ...S.btnGhost, color: C.cyanText }}>EDIT</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const S: Record<string, CSSProperties> = {
  root: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
    padding: 18,
    gap: 14,
    overflow: 'auto'
  },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between'
  },
  h1: {
    fontSize: 18,
    fontWeight: 700,
    fontFamily: F.display,
    letterSpacing: 1,
    color: C.text
  },
  h1Sub: {
    fontSize: 11,
    color: C.textDim,
    fontFamily: F.mono,
    marginTop: 3,
    letterSpacing: 0.4
  },
  panel: {
    background: C.bgPanel,
    border: `1px solid ${C.line}`,
    padding: 14,
    overflow: 'auto',
    flex: 1
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 11.5,
    fontFamily: F.mono
  },
  th: {
    textAlign: 'left',
    padding: '8px 10px',
    color: C.textDim,
    fontSize: 9.5,
    letterSpacing: 1,
    fontWeight: 700,
    borderBottom: `1px solid ${C.line}`
  },
  td: {
    padding: '8px 10px',
    borderBottom: `1px solid ${C.line2}`,
    color: C.cyan
  },
  chip: {
    padding: '2px 7px',
    border: '1px solid',
    fontSize: 9.5,
    fontFamily: F.mono,
    fontWeight: 700,
    letterSpacing: 0.4,
    textTransform: 'uppercase'
  },
  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '4px 10px',
    fontFamily: F.mono,
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none'
  }
}
