import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { StageRunnerModal } from '../../components/StageRunnerModal'
import { copyPacket } from '../../lib/copyPacket'
import type { ArtifactRead, ResponseSlot } from '../../../../shared/contract'
import { clipCard, colors as C, fonts as F } from '../../styles/tokens'

// Fixed paths the CLI stages reference. Pasted JSON is written here by
// writeResponseInput; builds read from these and write the markdown artifacts.
// All relative to the repo root (the stage runner spawns with cwd = REPO_ROOT).
const DECISION_DIR = 'reports/generated/decision'
const PATHS = {
  gpt: `${DECISION_DIR}/model_gpt_response.json`,
  claude: `${DECISION_DIR}/model_claude_response.json`,
  adjudicator: `${DECISION_DIR}/adjudicator_output.json`,
  packet: 'reports/generated/packet.md',
  adjInput: 'reports/generated/adjudicator_input.md',
  ticket: 'reports/generated/trade_ticket.md'
} as const

interface RunArgs {
  stage: string
  args?: string[]
}

export const DecisionScreen = () => {
  const [runArgs, setRunArgs] = useState<RunArgs | null>(null)
  const [text, setText] = useState<Record<ResponseSlot, string>>({
    gpt: '',
    claude: '',
    adjudicator: ''
  })
  const [artifacts, setArtifacts] = useState<{
    packet: ArtifactRead | null
    adjInput: ArtifactRead | null
    ticket: ArtifactRead | null
  }>({ packet: null, adjInput: null, ticket: null })

  const loadAll = useCallback(async (): Promise<void> => {
    const [packet, adjInput, ticket] = await Promise.all([
      window.pm.readArtifact('packet'),
      window.pm.readArtifact('adjudicator-input'),
      window.pm.readArtifact('trade-ticket')
    ])
    setArtifacts({ packet, adjInput, ticket })
  }, [])

  useEffect(() => {
    void loadAll()
    const off = window.pm.onContextChange(() => {
      void loadAll()
    })
    return off
  }, [loadAll])

  const validateResponse = async (slot: ResponseSlot): Promise<void> => {
    const path = await window.pm.writeResponseInput(slot, text[slot])
    const stage = slot === 'adjudicator' ? 'validate-adjudicator' : 'validate-response'
    setRunArgs({ stage, args: [path] })
  }

  const buildAdjudicatorInput = (): void => {
    setRunArgs({
      stage: 'build-adjudicator-input',
      args: [
        '--packet',
        PATHS.packet,
        '--model-output-a',
        PATHS.gpt,
        '--model-output-b',
        PATHS.claude,
        '--output',
        PATHS.adjInput
      ]
    })
  }

  const buildTradeTicket = (): void => {
    setRunArgs({
      stage: 'build-trade-ticket',
      args: ['--adjudicator-output', PATHS.adjudicator, '--output', PATHS.ticket]
    })
  }

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div style={S.h1}>DECISION</div>
        <div style={S.h1Sub}>
          // paste model replies → validate → build adjudicator input → paste verdict → trade ticket
        </div>
      </div>

      <div style={S.scroll}>
        <PasteStep
          n={1}
          title="GPT RESPONSE"
          sub="Paste the JSON the GPT risk tab returned. Validated against schemas/model_trade_response.schema.json (model-output-a)."
          value={text.gpt}
          onChange={(v) => setText((p) => ({ ...p, gpt: v }))}
          onRun={() => void validateResponse('gpt')}
          runLabel="write & validate gpt"
        />

        <PasteStep
          n={2}
          title="CLAUDE RESPONSE"
          sub="Paste the JSON the Claude trader tab returned. Same schema (model-output-b)."
          value={text.claude}
          onChange={(v) => setText((p) => ({ ...p, claude: v }))}
          onRun={() => void validateResponse('claude')}
          runLabel="write & validate claude"
        />

        <BuildStep
          n={3}
          title="ADJUDICATOR INPUT"
          sub="Combines packet.md + both validated responses into adjudicator_input.md. Copy it into the adjudicator tab."
          runLabel="build adjudicator input"
          onRun={buildAdjudicatorInput}
          warn={
            !artifacts.packet?.exists
              ? 'packet.md not built yet — build it on the PACKET tab first'
              : null
          }
          artifact={artifacts.adjInput}
        />

        <PasteStep
          n={4}
          title="ADJUDICATOR OUTPUT"
          sub="Paste the adjudicator's verdict JSON. Validated against schemas/adjudicator_output.schema.json."
          value={text.adjudicator}
          onChange={(v) => setText((p) => ({ ...p, adjudicator: v }))}
          onRun={() => void validateResponse('adjudicator')}
          runLabel="write & validate verdict"
        />

        <BuildStep
          n={5}
          title="TRADE TICKET"
          sub="Renders the human-reviewed trade_ticket.md (and ledger-ready trade_ticket.json) from the verdict."
          runLabel="build trade ticket"
          onRun={buildTradeTicket}
          warn={null}
          artifact={artifacts.ticket}
        />
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

const StepShell = ({
  n,
  title,
  sub,
  children
}: {
  n: number
  title: string
  sub: string
  children: ReactNode
}) => (
  <div style={S.step}>
    <div style={S.stepHdr}>
      <span style={S.stepNum}>{n}</span>
      <span style={S.stepTitle}>{title}</span>
    </div>
    <div style={S.stepSub}>{sub}</div>
    {children}
  </div>
)

const PasteStep = ({
  n,
  title,
  sub,
  value,
  onChange,
  onRun,
  runLabel
}: {
  n: number
  title: string
  sub: string
  value: string
  onChange: (v: string) => void
  onRun: () => void
  runLabel: string
}) => (
  <StepShell n={n} title={title} sub={sub}>
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      spellCheck={false}
      placeholder={'{\n  ...\n}'}
      style={S.textarea}
    />
    <div style={S.actions}>
      <button
        style={{ ...S.btnPrimary, opacity: value.trim() ? 1 : 0.4 }}
        onClick={onRun}
        disabled={!value.trim()}
      >
        ▸ {runLabel.toUpperCase()}
      </button>
    </div>
  </StepShell>
)

const BuildStep = ({
  n,
  title,
  sub,
  runLabel,
  onRun,
  warn,
  artifact
}: {
  n: number
  title: string
  sub: string
  runLabel: string
  onRun: () => void
  warn: string | null
  artifact: ArtifactRead | null
}) => {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle')
  const exists = artifact?.exists ?? false

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

  return (
    <StepShell n={n} title={title} sub={sub}>
      {warn && <div style={S.warn}>● {warn}</div>}
      <div style={S.actions}>
        <button style={S.btnGhost} onClick={onRun}>
          $ {runLabel}
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
              : '⎘ COPY'}
        </button>
      </div>
      {exists ? (
        <pre style={S.code}>{artifact!.content}</pre>
      ) : (
        <div style={S.empty}>
          run <span style={{ color: C.magenta, fontFamily: F.mono }}>$ {runLabel}</span> to generate
        </div>
      )}
    </StepShell>
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
    overflow: 'hidden'
  },
  header: { flexShrink: 0 },
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
  scroll: {
    flex: 1,
    minHeight: 0,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    paddingRight: 4
  },
  step: {
    background: C.bgPanel,
    border: `1px solid ${C.line}`,
    clipPath: clipCard,
    padding: 14,
    display: 'flex',
    flexDirection: 'column',
    gap: 8
  },
  stepHdr: { display: 'flex', alignItems: 'center', gap: 10 },
  stepNum: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 20,
    height: 20,
    background: C.magenta,
    color: C.bg,
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    boxShadow: `0 0 10px ${C.magenta}88`
  },
  stepTitle: {
    fontFamily: F.mono,
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: 0.6,
    color: C.text
  },
  stepSub: { fontSize: 11.5, color: C.textDim, lineHeight: 1.5 },
  textarea: {
    minHeight: 160,
    background: C.bg,
    color: C.text,
    border: `1px solid ${C.line2}`,
    padding: 12,
    fontFamily: F.mono,
    fontSize: 12,
    lineHeight: 1.5,
    resize: 'vertical',
    outline: 'none'
  },
  actions: { display: 'flex', gap: 8, alignItems: 'center' },
  warn: {
    fontFamily: F.mono,
    fontSize: 11,
    color: C.amber,
    textShadow: `0 0 4px ${C.amber}66`
  },
  code: {
    background: C.bg,
    border: `1px solid ${C.line2}`,
    padding: 12,
    margin: 0,
    fontFamily: F.mono,
    fontSize: 11,
    lineHeight: 1.5,
    color: C.text,
    whiteSpace: 'pre-wrap',
    maxHeight: 280,
    overflowY: 'auto'
  },
  empty: {
    fontFamily: F.mono,
    fontSize: 11.5,
    color: C.textMute,
    padding: '10px 0'
  },
  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '8px 14px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none'
  },
  btnPrimary: {
    background: C.magenta,
    color: C.bg,
    border: 'none',
    padding: '8px 16px',
    fontFamily: F.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.8,
    cursor: 'pointer',
    textTransform: 'uppercase',
    boxShadow: `0 0 14px ${C.magenta}88`,
    outline: 'none'
  }
}
