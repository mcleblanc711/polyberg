import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { StageRunnerModal } from '../../components/StageRunnerModal'
import { usePmData } from '../../lib/pmDataContext'
import type { ArtifactName, ArtifactRead } from '../../../../shared/contract'
import { colors as C, fonts as F } from '../../styles/tokens'

interface ArtifactSpec {
  name: ArtifactName
  label: string
  filename: string
  buildStage: string
  hint: string
  promptHint: string
}

const SPECS: ArtifactSpec[] = [
  {
    name: 'packet',
    label: 'PACKET',
    filename: 'reports/generated/packet.md',
    buildStage: 'build-packet',
    hint: 'paste into Claude trader and ChatGPT risk tabs',
    promptHint: 'prompts/claude_trader_prompt.md  +  prompts/chatgpt_risk_prompt.md'
  },
  {
    name: 'adjudicator-input',
    label: 'ADJUDICATOR INPUT',
    filename: 'reports/generated/adjudicator_input.md',
    buildStage: 'build-adjudicator-input',
    hint: 'paste into adjudicator model after both model outputs are validated',
    promptHint: 'prompts/adjudicator_prompt.md'
  }
]

const PACKET_INPUT_FILES = new Set([
  'live_state.yaml',
  'portfolio_current.yaml',
  'open_orders.yaml',
  'recent_catalysts.md',
  'market_registry.yaml'
])

type Severity = 'info' | 'warn' | 'rebuild' | 'block'

interface RunArgs {
  stage: string
  args?: string[]
}

interface Warning {
  severity: Severity
  text: string
  hint?: string
  run?: RunArgs
  runLabel?: string
}

const sevColor = (s: Severity): string =>
  s === 'block' ? C.red : s === 'rebuild' ? C.magenta : s === 'warn' ? C.amber : C.cyan

const fmtBytes = (n: number): string => {
  if (n === 0) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

const fmtAge = (mins: number | null): string => {
  if (mins === null) return '—'
  if (mins < 60) return `${mins}m ago`
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`
  return `${Math.round(mins / 1440)}d ago`
}

const ageColor = (mins: number | null): string => {
  if (mins === null) return C.textMute
  if (mins < 120) return C.cyan
  if (mins < 1440) return C.amber
  return C.red
}

export const PacketScreen = () => {
  const [runArgs, setRunArgs] = useState<RunArgs | null>(null)
  const [artifacts, setArtifacts] = useState<Record<ArtifactName, ArtifactRead | null>>({
    packet: null,
    'adjudicator-input': null
  })

  const loadOne = useCallback(async (name: ArtifactName): Promise<void> => {
    const data = await window.pm.readArtifact(name)
    setArtifacts((prev) => ({ ...prev, [name]: data }))
  }, [])

  const loadAll = useCallback(async (): Promise<void> => {
    await Promise.all(SPECS.map((s) => loadOne(s.name)))
  }, [loadOne])

  useEffect(() => {
    void loadAll()
    const off = window.pm.onContextChange(() => {
      void loadAll()
    })
    return off
  }, [loadAll])

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <div style={S.h1}>PACKET REVIEW</div>
          <div style={S.h1Sub}>
            // build → copy → paste into web LLM → save reply JSON → run next stage
          </div>
        </div>
      </div>
      <div style={S.grid}>
        {SPECS.map((spec) => (
          <ArtifactPanel
            key={spec.name}
            spec={spec}
            artifact={artifacts[spec.name]}
            otherArtifacts={artifacts}
            onRun={(r) => setRunArgs(r)}
          />
        ))}
      </div>
      {runArgs && (
        <StageRunnerModal
          stage={runArgs.stage}
          args={runArgs.args}
          onClose={() => {
            setRunArgs(null)
            void loadAll()
          }}
        />
      )}
    </div>
  )
}

const ArtifactPanel = ({
  spec,
  artifact,
  otherArtifacts,
  onRun
}: {
  spec: ArtifactSpec
  artifact: ArtifactRead | null
  otherArtifacts: Record<ArtifactName, ArtifactRead | null>
  onRun: (r: RunArgs) => void
}) => {
  const pmData = usePmData()
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle')

  useEffect(() => {
    if (copyState === 'idle') return
    const t = setTimeout(() => setCopyState('idle'), 1800)
    return () => clearTimeout(t)
  }, [copyState])

  const onCopy = async (): Promise<void> => {
    if (!artifact?.exists) return
    try {
      await window.pm.writeClipboard(artifact.content)
      setCopyState('copied')
      return
    } catch {
      /* fall through */
    }
    try {
      await navigator.clipboard.writeText(artifact.content)
      setCopyState('copied')
    } catch {
      setCopyState('error')
    }
  }

  const exists = artifact?.exists ?? false
  const ageC = ageColor(artifact?.ageMin ?? null)
  const warnings = computeWarnings(spec, artifact, otherArtifacts, pmData)

  return (
    <div style={S.panel}>
      <div style={S.panelHdr}>
        // {spec.filename}
        <span style={{ flex: 1 }} />
        {exists ? (
          <>
            <span style={{ color: ageC, textShadow: `0 0 4px ${ageC}66` }}>
              ● {fmtAge(artifact!.ageMin)}
            </span>
            <span style={S.metaSep}>·</span>
            <span style={S.metaDim}>{fmtBytes(artifact!.bytes)}</span>
          </>
        ) : (
          <span style={{ color: C.textMute }}>● not built</span>
        )}
      </div>

      <div style={S.actions}>
        <button style={S.btnGhost} onClick={() => onRun({ stage: spec.buildStage })}>
          $ {spec.buildStage}
        </button>
        <button
          style={{
            ...S.btnPrimary,
            opacity: exists ? 1 : 0.4,
            cursor: exists ? 'pointer' : 'not-allowed'
          }}
          onClick={onCopy}
          disabled={!exists}
        >
          {copyState === 'copied'
            ? '✓ COPIED'
            : copyState === 'error'
              ? '✕ COPY FAILED'
              : '⎘ COPY TO CLIPBOARD'}
        </button>
      </div>

      {warnings.length > 0 && (
        <div style={S.warnBox}>
          <div style={S.warnHdr}>// prerequisites</div>
          {warnings.map((w, i) => (
            <div key={i} style={S.warnRow}>
              <span style={{ ...S.warnDot, background: sevColor(w.severity) }} />
              <div style={{ flex: 1 }}>
                <div style={{ ...S.warnText, color: sevColor(w.severity) }}>{w.text}</div>
                {w.hint && <div style={S.warnHint}>{w.hint}</div>}
              </div>
              {w.run && w.runLabel && (
                <button
                  style={{
                    ...S.warnBtn,
                    color: sevColor(w.severity),
                    borderColor: sevColor(w.severity)
                  }}
                  onClick={() => onRun(w.run!)}
                >
                  {w.runLabel}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={S.hintBox}>
        <div style={S.hintLine}>{spec.hint}</div>
        <div style={S.hintMono}>{spec.promptHint}</div>
      </div>

      {exists ? (
        <pre style={S.code}>{artifact!.content}</pre>
      ) : (
        <div style={S.empty}>
          run <span style={{ color: C.magenta, fontFamily: F.mono }}>$ {spec.buildStage}</span> to
          generate this file
        </div>
      )}
    </div>
  )
}

const computeWarnings = (
  spec: ArtifactSpec,
  artifact: ArtifactRead | null,
  otherArtifacts: Record<ArtifactName, ArtifactRead | null>,
  pmData: ReturnType<typeof usePmData>
): Warning[] => {
  const warnings: Warning[] = []
  const artifactAge = artifact?.exists ? artifact.ageMin : null

  if (spec.name === 'packet') {
    const snap = pmData.snapshots[0]
    if (!snap) {
      warnings.push({
        severity: 'warn',
        text: 'no market snapshot in data/snapshots/',
        hint: 'snapshot-markets is currently a stub — prices will be None; run anyway to populate the structure',
        run: { stage: 'snapshot-markets' },
        runLabel: '$ snapshot-markets'
      })
    } else if (snap.freshMin > 120) {
      warnings.push({
        severity: 'warn',
        text: `latest snapshot is ${fmtAge(snap.freshMin)} (${snap.ts})`,
        hint: 'snapshot-markets is currently a stub — prices will be None',
        run: { stage: 'snapshot-markets' },
        runLabel: '$ snapshot-markets'
      })
    }

    if (artifact?.exists && artifactAge !== null) {
      const newerInputs = pmData.freshness.filter(
        (f) => PACKET_INPUT_FILES.has(f.file) && f.age < artifactAge - 1
      )
      if (newerInputs.length > 0) {
        const names = newerInputs.map((f) => f.file).join(', ')
        warnings.push({
          severity: 'rebuild',
          text: `input changed since last build: ${names}`,
          hint: `packet was built ${fmtAge(artifactAge)}; inputs updated more recently`,
          run: { stage: 'build-packet' },
          runLabel: '$ rebuild packet'
        })
      }
    }

    pmData.freshness
      .filter((f) => PACKET_INPUT_FILES.has(f.file) && f.state === 'stale')
      .forEach((f) => {
        warnings.push({
          severity: 'warn',
          text: `${f.file} is stale (${fmtAge(f.age)})`,
          hint: 'refresh this input before rebuilding the packet for accurate context'
        })
      })

    const missingTokenCount = pmData.markets.filter(
      (m) => !m.windows || (m.windows.d1.high === 0 && m.windows.d1.low === 0)
    ).length
    if (!artifact?.exists && pmData.markets.length === 0) {
      warnings.push({
        severity: 'block',
        text: 'no markets in registry — packet will be empty'
      })
    }
    void missingTokenCount

    if (!artifact?.exists) {
      warnings.push({
        severity: 'info',
        text: 'packet not built yet — click $ build-packet above'
      })
    }
  }

  if (spec.name === 'adjudicator-input') {
    const packet = otherArtifacts.packet
    if (!packet?.exists) {
      warnings.push({
        severity: 'block',
        text: 'no packet to adjudicate — build packet.md first',
        run: { stage: 'build-packet' },
        runLabel: '$ build-packet'
      })
    } else if (
      artifact?.exists &&
      artifactAge !== null &&
      packet.ageMin !== null &&
      packet.ageMin < artifactAge - 1
    ) {
      warnings.push({
        severity: 'rebuild',
        text: `packet rebuilt ${fmtAge(packet.ageMin)} — adjudicator input is older`,
        hint: 'rebuild adjudicator input so it reflects the current packet',
        run: { stage: 'build-adjudicator-input' },
        runLabel: '$ rebuild'
      })
    }

    if (!artifact?.exists && packet?.exists) {
      warnings.push({
        severity: 'info',
        text: 'adjudicator input not built yet — needs validated claude_output.json + chatgpt_output.json'
      })
    }
  }

  return warnings
}

const S: Record<string, CSSProperties> = {
  root: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
    padding: 18,
    gap: 14,
    overflow: 'hidden'
  },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    flexShrink: 0
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
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 12,
    flex: 1,
    minHeight: 0
  },
  panel: {
    background: C.bgPanel,
    border: `1px solid ${C.line}`,
    padding: 14,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
    gap: 10
  },
  panelHdr: {
    fontSize: 10,
    color: C.magenta,
    letterSpacing: 0.8,
    fontWeight: 700,
    fontFamily: F.mono,
    textShadow: `0 0 4px ${C.magenta}66`,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    flexShrink: 0
  },
  metaSep: { color: C.textMute, fontFamily: F.mono },
  metaDim: { color: C.textDim, fontFamily: F.mono },
  actions: { display: 'flex', gap: 8, flexShrink: 0 },
  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.cyan}`,
    color: C.cyan,
    padding: '6px 12px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 0.7,
    cursor: 'pointer',
    textTransform: 'uppercase',
    boxShadow: `0 0 8px ${C.cyan}33`,
    outline: 'none'
  },
  btnPrimary: {
    background: C.magenta,
    color: C.bg,
    border: 'none',
    padding: '6px 14px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    boxShadow: `0 0 12px ${C.magenta}88`,
    outline: 'none',
    marginLeft: 'auto'
  },
  warnBox: {
    background: C.bg,
    border: `1px solid ${C.line2}`,
    padding: '8px 10px',
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: 6
  },
  warnHdr: {
    fontSize: 10,
    color: C.textMute,
    fontFamily: F.mono,
    letterSpacing: 0.7,
    fontWeight: 700
  },
  warnRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10
  },
  warnDot: {
    width: 6,
    height: 6,
    flexShrink: 0,
    marginTop: 2,
    alignSelf: 'flex-start'
  },
  warnText: {
    fontSize: 11,
    fontFamily: F.mono,
    letterSpacing: 0.3,
    lineHeight: 1.4
  },
  warnHint: {
    fontSize: 10.5,
    color: C.textDim,
    fontFamily: F.body,
    marginTop: 2,
    lineHeight: 1.4
  },
  warnBtn: {
    background: 'transparent',
    border: '1px solid',
    padding: '4px 10px',
    fontFamily: F.mono,
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none',
    flexShrink: 0
  },
  hintBox: {
    background: C.bgRow,
    border: `1px solid ${C.line2}`,
    padding: '8px 10px',
    flexShrink: 0
  },
  hintLine: {
    fontSize: 11,
    color: C.textDim,
    fontFamily: F.body,
    lineHeight: 1.4
  },
  hintMono: {
    fontSize: 10.5,
    color: C.cyan,
    fontFamily: F.mono,
    marginTop: 4,
    letterSpacing: 0.3
  },
  code: {
    background: C.bg,
    border: `1px solid ${C.line2}`,
    padding: 12,
    fontFamily: F.mono,
    fontSize: 11.5,
    color: C.text,
    lineHeight: 1.55,
    margin: 0,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    flex: 1,
    minHeight: 0,
    overflow: 'auto'
  },
  empty: {
    flex: 1,
    border: `1px dashed ${C.line}`,
    padding: 24,
    color: C.textMute,
    fontFamily: F.mono,
    fontSize: 11.5,
    textAlign: 'center',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center'
  }
}
