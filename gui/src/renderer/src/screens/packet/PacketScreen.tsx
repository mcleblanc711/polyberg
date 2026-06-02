import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { StageRunnerModal } from '../../components/StageRunnerModal'
import { copyPacket } from '../../lib/copyPacket'
import { usePmData } from '../../lib/pmDataContext'
import type { ArtifactName, ArtifactRead } from '../../../../shared/contract'
import { colors as C, fonts as F } from '../../styles/tokens'

interface ArtifactSpec {
  name: ArtifactName
  label: string
  filename: string
  buildStage: string
  buildArgs?: string[]
  buildLabel: string
  copyLabel: string
  hint: string
  promptHint: string
}

const SPECS: ArtifactSpec[] = [
  {
    name: 'packet-gpt',
    label: 'GPT PACKET',
    filename: 'reports/generated/Polyberg_Current_Research_Packet_GPT_Source.md',
    buildStage: 'packet',
    buildArgs: ['build', '--target', 'gpt', '--output-dir', 'reports/generated'],
    buildLabel: 'generate gpt packet',
    copyLabel: 'copy gpt packet',
    hint: 'verbose, layer-separated source — paste into a GPT research/risk tab',
    promptHint: 'Polyberg_Current_Research_Packet_GPT_Source.md  +  polymarket_rules.md'
  },
  {
    name: 'packet-claude',
    label: 'CLAUDE PACKET',
    filename: 'reports/generated/Polyberg_Current_Research_Packet_Claude_Source.md',
    buildStage: 'packet',
    buildArgs: ['build', '--target', 'claude', '--output-dir', 'reports/generated'],
    buildLabel: 'generate claude packet',
    copyLabel: 'copy claude packet',
    hint: 'concise, adversarial source — paste into a Claude trader tab',
    promptHint: 'Polyberg_Current_Research_Packet_Claude_Source.md  +  polymarket_rules.md'
  },
  {
    name: 'packet',
    label: 'PACKET (LEGACY)',
    filename: 'reports/generated/packet.md',
    buildStage: 'build-packet',
    buildLabel: 'build-packet',
    copyLabel: 'copy to clipboard',
    hint: 'paste into Claude trader and ChatGPT risk tabs',
    promptHint: 'prompts/claude_trader_prompt.md  +  prompts/chatgpt_risk_prompt.md'
  }
  // The adjudicator-input step (and the rest of the decision leg) lives on the
  // DECISION tab now — it needs pasted model responses as build args, which a
  // plain artifact panel can't supply.
]

// Per-session market data whose age should gate a packet rebuild. Deliberately
// excludes market_registry.yaml: it's a stable catalog of tracked markets
// (config, not market data), so its mtime going past 24h is a false staleness
// alarm — same reasoning that kept live_state.yaml out of the freshness checks.
const PACKET_INPUT_FILES = new Set([
  'portfolio_current.yaml',
  'open_orders.yaml',
  'recent_catalysts.md'
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
  const [artifacts, setArtifacts] = useState<Partial<Record<ArtifactName, ArtifactRead | null>>>({
    packet: null,
    'packet-gpt': null,
    'packet-claude': null
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
            artifact={artifacts[spec.name] ?? null}
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
  onRun
}: {
  spec: ArtifactSpec
  artifact: ArtifactRead | null
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
    const outcome = await copyPacket(artifact.content, {
      writeClipboard: (t) => window.pm.writeClipboard(t),
      navigatorWrite: (t) => navigator.clipboard.writeText(t)
    })
    setCopyState(outcome)
  }

  const exists = artifact?.exists ?? false
  const ageC = ageColor(artifact?.ageMin ?? null)
  const warnings = computeWarnings(spec, artifact, pmData)

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
        <button
          style={S.btnGhost}
          onClick={() => onRun({ stage: spec.buildStage, args: spec.buildArgs })}
        >
          $ {spec.buildLabel}
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
              : `⎘ ${spec.copyLabel.toUpperCase()}`}
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
          run <span style={{ color: C.magenta, fontFamily: F.mono }}>$ {spec.buildLabel}</span> to
          generate this file
        </div>
      )}
    </div>
  )
}

const computeWarnings = (
  spec: ArtifactSpec,
  artifact: ArtifactRead | null,
  pmData: ReturnType<typeof usePmData>
): Warning[] => {
  const warnings: Warning[] = []
  const artifactAge = artifact?.exists ? artifact.ageMin : null
  const isModelPacket = spec.name === 'packet-gpt' || spec.name === 'packet-claude'

  if (spec.name === 'packet' || isModelPacket) {
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
          run: { stage: spec.buildStage, args: spec.buildArgs },
          runLabel: `$ ${spec.buildLabel}`
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
        text: `packet not built yet — click $ ${spec.buildLabel} above`
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
