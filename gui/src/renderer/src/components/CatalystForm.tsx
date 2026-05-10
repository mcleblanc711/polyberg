import { useState, type CSSProperties } from 'react'
import { colors as C, fonts as F } from '../styles/tokens'

const nowIsoCompact = (): string => new Date().toISOString().slice(0, 16) + 'Z'

export const CatalystForm = ({
  marketId,
  onCancel,
  onSaved
}: {
  marketId: string
  onCancel: () => void
  onSaved?: () => void
}) => {
  const [t, setT] = useState(nowIsoCompact())
  const [src, setSrc] = useState('')
  const [txt, setTxt] = useState('')
  const [status, setStatus] = useState<'idle' | 'writing' | 'err'>('idle')
  const [err, setErr] = useState<string | null>(null)

  const valid = t.trim() !== '' && src.trim() !== '' && txt.trim() !== ''

  const submit = async (): Promise<void> => {
    if (!valid) return
    setStatus('writing')
    setErr(null)
    try {
      await window.pm.appendCatalyst(marketId, { t, src, txt })
      onSaved?.()
      onCancel()
    } catch (e) {
      setStatus('err')
      setErr(String(e))
    }
  }

  return (
    <div style={S.box}>
      <div style={S.hdr}>
        // new catalyst → recent_catalysts.md · {marketId}
      </div>
      <div style={S.row}>
        <div style={{ flex: '0 0 180px' }}>
          <div style={S.k}>TIMESTAMP</div>
          <input value={t} onChange={(e) => setT(e.target.value)} style={S.input} />
        </div>
        <div style={{ flex: '0 0 200px' }}>
          <div style={S.k}>SOURCE</div>
          <input
            value={src}
            onChange={(e) => setSrc(e.target.value)}
            placeholder="Reuters / WSJ / @handle"
            style={S.input}
          />
        </div>
        <div style={{ flex: 1 }}>
          <div style={S.k}>BODY</div>
          <input
            value={txt}
            onChange={(e) => setTxt(e.target.value)}
            placeholder="one-line catalyst note"
            style={S.input}
          />
        </div>
      </div>
      <div style={S.actions}>
        <button
          onClick={submit}
          disabled={!valid || status === 'writing'}
          style={{
            ...S.btnPrimary,
            opacity: valid && status !== 'writing' ? 1 : 0.5,
            cursor: valid && status !== 'writing' ? 'pointer' : 'not-allowed'
          }}
        >
          {status === 'writing' ? 'APPENDING…' : '✓ APPEND'}
        </button>
        <button onClick={onCancel} style={S.btnGhost}>
          ✕ CANCEL
        </button>
        {status === 'err' && (
          <span style={{ marginLeft: 'auto', color: C.red, fontFamily: F.mono, fontSize: 10.5 }}>
            {err}
          </span>
        )}
      </div>
    </div>
  )
}

const S: Record<string, CSSProperties> = {
  box: {
    background: C.bgRow,
    border: `1px solid ${C.magenta}`,
    boxShadow: `0 0 12px ${C.magenta}44`,
    padding: 12,
    marginBottom: 12
  },
  hdr: {
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 0.8,
    fontWeight: 700,
    fontFamily: F.mono,
    textShadow: `0 0 4px ${C.magenta}66`,
    marginBottom: 10
  },
  row: { display: 'flex', gap: 10, marginBottom: 10 },
  k: { fontSize: 9.5, color: C.textDim, letterSpacing: 1, fontFamily: F.mono, fontWeight: 600 },
  input: {
    width: '100%',
    background: C.bg,
    border: `1px solid ${C.line}`,
    color: C.text,
    fontFamily: F.mono,
    fontSize: 12,
    padding: '6px 8px',
    marginTop: 4,
    outline: 'none'
  },
  actions: { display: 'flex', gap: 8, alignItems: 'center' },
  btnPrimary: {
    background: C.magenta,
    color: C.bg,
    border: 'none',
    padding: '6px 14px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.8,
    boxShadow: `0 0 10px ${C.magenta}66`,
    outline: 'none'
  },
  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '6px 12px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 600,
    letterSpacing: 0.6,
    cursor: 'pointer',
    outline: 'none'
  }
}
