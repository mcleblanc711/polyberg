import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { isAllowedStage, type RunStageResult } from '../../../shared/contract'
import { colors as C, fonts as F } from '../styles/tokens'

interface Chunk {
  stream: 'stdout' | 'stderr'
  text: string
}

export const StageRunnerModal = ({
  stage,
  args,
  onClose
}: {
  stage: string
  args?: string[]
  onClose: () => void
}) => {
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [result, setResult] = useState<RunStageResult | null>(null)
  const [running, setRunning] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const preRef = useRef<HTMLPreElement>(null)
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    if (!isAllowedStage(stage)) {
      setError(`Stage "${stage}" is not in the allowlist`)
      setRunning(false)
      return
    }
    void window.pm
      .runStageStream(stage, args ?? [], (chunk) => {
        setChunks((prev) => [...prev, chunk])
      })
      .then((r) => {
        setResult(r)
        setRunning(false)
      })
      .catch((e) => {
        setError(String(e))
        setRunning(false)
      })
  }, [stage, args])

  useEffect(() => {
    const el = preRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [chunks])

  const headerColor = running
    ? C.amber
    : result?.ok
      ? C.cyan
      : C.red
  const status = running
    ? 'RUNNING…'
    : error
      ? `ERROR · ${error}`
      : result?.ok
        ? `EXIT 0 · OK`
        : `EXIT ${result?.code ?? '?'} · FAILED`

  return (
    <div style={S.overlay} onClick={running ? undefined : onClose}>
      <div style={S.modal} onClick={(e) => e.stopPropagation()}>
        <div style={S.hdr}>
          <div>
            <div style={S.title}>$ polyberg {stage}{args?.length ? ' ' + args.join(' ') : ''}</div>
            <div style={{ ...S.status, color: headerColor, textShadow: `0 0 6px ${headerColor}66` }}>
              ● {status}
            </div>
          </div>
          <button style={S.btnGhost} onClick={onClose} disabled={running}>
            {running ? 'WORKING…' : '✕ CLOSE'}
          </button>
        </div>
        <pre ref={preRef} style={S.body}>
          {chunks.map((c, i) => (
            <span key={i} style={{ color: c.stream === 'stderr' ? C.red : C.cyan }}>
              {c.text}
            </span>
          ))}
          {chunks.length === 0 && !error ? (
            <span style={{ color: C.textMute }}>// no output yet…</span>
          ) : null}
        </pre>
      </div>
    </div>
  )
}

const S: Record<string, CSSProperties> = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0, 0, 0, 0.65)',
    backdropFilter: 'blur(2px)',
    zIndex: 100,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center'
  },
  modal: {
    width: '80vw',
    maxWidth: 1100,
    height: '70vh',
    background: C.bgPanel,
    border: `1px solid ${C.magenta}`,
    boxShadow: `0 0 20px ${C.magenta}66`,
    display: 'flex',
    flexDirection: 'column'
  },
  hdr: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 18px',
    borderBottom: `1px solid ${C.line}`,
    background: C.bg,
    flexShrink: 0
  },
  title: {
    fontFamily: F.mono,
    fontSize: 13,
    fontWeight: 700,
    color: C.text,
    letterSpacing: 0.4
  },
  status: {
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 0.8,
    marginTop: 4
  },
  body: {
    flex: 1,
    margin: 0,
    padding: 16,
    background: C.bg,
    fontFamily: F.mono,
    fontSize: 11.5,
    color: C.text,
    lineHeight: 1.5,
    overflowY: 'auto',
    whiteSpace: 'pre-wrap'
  },
  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '6px 12px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none'
  }
}
