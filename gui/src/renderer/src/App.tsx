import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { StageRunnerModal } from './components/StageRunnerModal'
import { nextRunnableStage } from './lib/pmData'
import { usePmData, usePmDataRefresh } from './lib/pmDataContext'
import { useLocalState } from './lib/useLocalState'
import type { IntakeItem, Market } from './lib/types'
import { AccountScreen } from './screens/account/AccountScreen'
import { DashboardScreen } from './screens/dashboard/DashboardScreen'
import { CatalystsScreen } from './screens/catalysts/CatalystsScreen'
import { IntakeScreen } from './screens/intake/IntakeScreen'
import { MarketsScreen } from './screens/markets/MarketsScreen'
import { PacketScreen } from './screens/packet/PacketScreen'
import { DecisionScreen } from './screens/decision/DecisionScreen'
import { SnapshotsScreen } from './screens/snapshots/SnapshotsScreen'
import { LadderScreen } from './screens/ladder/LadderScreen'
import { colors as C, fonts as F } from './styles/tokens'

type ScreenId =
  | 'dashboard'
  | 'intake'
  | 'snapshots'
  | 'catalysts'
  | 'packet'
  | 'decision'
  | 'ladder'
  | 'markets'
  | 'account'

interface Tab {
  id: ScreenId
  label: string
  badge?: number
}

const TopBar = ({
  screen,
  setScreen,
  nextLabel,
  nextEnabled,
  pendingIntake,
  onRunNextStage,
  onOpenPalette
}: {
  screen: ScreenId
  setScreen: (s: ScreenId) => void
  nextLabel: string
  nextEnabled: boolean
  pendingIntake: number
  onRunNextStage: () => void
  onOpenPalette: () => void
}) => {
  const pmData = usePmData()
  const refresh = usePmDataRefresh()
  const [refreshing, setRefreshing] = useState(false)
  const onRefresh = async (): Promise<void> => {
    if (refreshing) return
    setRefreshing(true)
    try {
      await refresh()
    } finally {
      setRefreshing(false)
    }
  }
  const tabs: Tab[] = [
    { id: 'dashboard', label: 'DASHBOARD' },
    { id: 'intake', label: 'INTAKE', badge: pendingIntake },
    { id: 'snapshots', label: 'SNAPSHOTS' },
    { id: 'catalysts', label: 'CATALYSTS' },
    { id: 'packet', label: 'PACKET' },
    { id: 'decision', label: 'DECISION' },
    { id: 'ladder', label: 'LADDER' },
    { id: 'markets', label: 'MARKETS' },
    { id: 'account', label: 'ACCOUNT' }
  ]
  return (
    <div style={S.topBar}>
      <div style={S.brand}>
        <div style={S.brandMark}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path
              d="M4 18 L4 6 L12 12 L20 6 L20 18"
              stroke={C.magenta}
              strokeWidth={2.5}
              strokeLinejoin="round"
              strokeLinecap="round"
              style={{ filter: `drop-shadow(0 0 3px ${C.magenta})` }}
            />
          </svg>
        </div>
        <div style={S.brandText}>polyberg / terminal</div>
        <div style={S.brandVer}>v0.1.0</div>
      </div>
      <div style={S.tabs}>
        {tabs.map((t) => {
          const on = screen === t.id
          return (
            <button
              key={t.id}
              onClick={() => setScreen(t.id)}
              style={{ ...S.tab, ...(on ? S.tabActive : null) }}
            >
              {t.label}
              {t.badge ? <span style={on ? S.tabBadgeOn : S.tabBadge}>{t.badge}</span> : null}
            </button>
          )
        })}
      </div>
      <button style={S.searchBar} onClick={onOpenPalette}>
        <span style={{ color: C.textMute }}>⌕</span>
        <span style={{ color: C.textMute, fontSize: 11 }}>jump to market…</span>
        <span style={S.kbd}>⌘K</span>
      </button>
      <div style={S.modeChip}>
        <span style={S.modeChipDot} />
        {pmData.liveState.mode}
      </div>
      <button style={S.btnGhost} onClick={onRefresh} disabled={refreshing}>
        {refreshing ? '$ …' : '$ REFRESH'}
      </button>
      <button
        style={{ ...S.btnPrimary, opacity: nextEnabled ? 1 : 0.45 }}
        onClick={onRunNextStage}
        disabled={!nextEnabled}
      >
        <span>RUN NEXT STAGE ▸</span>
        <span style={S.btnPrimarySub}>{nextLabel}</span>
      </button>
    </div>
  )
}

const StatusBar = ({ screen }: { screen: ScreenId }) => {
  const pmData = usePmData()
  const aging = pmData.freshness.filter((f) => f.state !== 'fresh')
  const active = pmData.markets.filter((m) => !m.expired).length
  const expired = pmData.markets.length - active
  const booksAt = pmData.markets.find((m) => m.bookStatus === 'ok')?.lastUpdate ?? ''
  return (
    <div style={S.statusBar}>
      <span style={{ color: C.cyan }}>● READ-ONLY</span>
      <span>
        SCREEN <span style={{ color: C.magenta }}>{screen.toUpperCase()}</span>
      </span>
      <span>
        {active} ACTIVE MKTS{expired > 0 ? ` · ${expired} EXPIRED` : ''}
      </span>
      <span style={{ flex: 1 }} />
      {booksAt && <span>BOOKS {booksAt.slice(11, 19)}</span>}
      <span>CTX LOADED {pmData.loadedAt}</span>
      {aging.length > 0 && (
        <span style={{ color: C.amber }}>
          ● {aging.length} ITEM{aging.length === 1 ? '' : 'S'} AGING
          {aging.length === 1 ? ` (${aging[0]!.file})` : ''}
        </span>
      )}
    </div>
  )
}

// ⌘K palette: substring-match against market ids and names, Enter/click jumps
// to the MARKETS screen with the row highlighted.
const JumpPalette = ({
  markets,
  onSelect,
  onClose
}: {
  markets: Market[]
  onSelect: (id: string) => void
  onClose: () => void
}) => {
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => inputRef.current?.focus(), [])

  const hits = useMemo(() => {
    const q = query.trim().toLowerCase()
    const pool = q
      ? markets.filter(
          (m) => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)
        )
      : markets.filter((m) => !m.expired)
    return pool.slice(0, 12)
  }, [markets, query])

  const clampedCursor = Math.min(cursor, Math.max(0, hits.length - 1))

  const onKey = (e: React.KeyboardEvent): void => {
    if (e.key === 'Escape') onClose()
    else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => Math.min(c + 1, hits.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => Math.max(c - 1, 0))
    } else if (e.key === 'Enter' && hits[clampedCursor]) {
      onSelect(hits[clampedCursor]!.id)
    }
  }

  return (
    <div style={S.paletteBackdrop} onClick={onClose}>
      <div style={S.paletteCard} onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          style={S.paletteInput}
          placeholder="jump to market — type id or name…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setCursor(0)
          }}
          onKeyDown={onKey}
        />
        <div style={S.paletteList}>
          {hits.length === 0 && <div style={S.paletteEmpty}>no markets match “{query}”</div>}
          {hits.map((m, i) => (
            <div
              key={m.id}
              onClick={() => onSelect(m.id)}
              onMouseEnter={() => setCursor(i)}
              style={{
                ...S.paletteRow,
                background: i === clampedCursor ? C.magentaDim : 'transparent'
              }}
            >
              <span
                style={{
                  color: i === clampedCursor ? C.magenta : C.text,
                  fontWeight: i === clampedCursor ? 700 : 400
                }}
              >
                {m.id}
              </span>
              <span style={S.paletteRowName}>{m.name}</span>
              {m.expired && <span style={S.paletteExpired}>EXPIRED</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export const App = () => {
  const pmData = usePmData()
  const [screen, setScreen] = useState<ScreenId>('dashboard')
  const [runningStage, setRunningStage] = useState<string | null>(null)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [highlightId, setHighlightId] = useState<string | null>(null)
  // Same key the IntakeScreen queue persists under; useLocalState keeps the
  // badge in sync with edits made on that screen.
  const [intakeQueue] = useLocalState<IntakeItem[]>('polyberg:intake.queue', pmData.intake)
  const pendingIntake = intakeQueue.filter((i) => i.status === 'suggested').length

  const next = nextRunnableStage(pmData.workflow)
  const nextLabel =
    pendingIntake > 0
      ? `review ${pendingIntake} intake item${pendingIntake === 1 ? '' : 's'}`
      : next
        ? `$ ${next.cli}`
        : 'all stages fresh'
  const nextEnabled = pendingIntake > 0 || next !== null

  const onRunNextStage = (): void => {
    if (pendingIntake > 0 && screen !== 'intake') {
      setScreen('intake')
      return
    }
    if (next) setRunningStage(next.cli)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((o) => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const jumpToMarket = (id: string): void => {
    setPaletteOpen(false)
    setHighlightId(id)
    setScreen('markets')
  }

  const renderScreen = (): JSX.Element => {
    switch (screen) {
      case 'dashboard':
        return <DashboardScreen onRunNextStage={onRunNextStage} nextLabel={nextLabel} nextEnabled={nextEnabled} />
      case 'markets':
        return <MarketsScreen highlightId={highlightId} onClearHighlight={() => setHighlightId(null)} />
      case 'packet':
        return <PacketScreen />
      case 'decision':
        return <DecisionScreen />
      case 'ladder':
        return <LadderScreen />
      case 'catalysts':
        return <CatalystsScreen />
      case 'snapshots':
        return <SnapshotsScreen />
      case 'intake':
        return <IntakeScreen />
      case 'account':
        return <AccountScreen />
    }
  }

  return (
    <>
      <div style={S.shell}>
        <TopBar
          screen={screen}
          setScreen={setScreen}
          nextLabel={nextLabel}
          nextEnabled={nextEnabled}
          pendingIntake={pendingIntake}
          onRunNextStage={onRunNextStage}
          onOpenPalette={() => setPaletteOpen(true)}
        />
        <div style={S.body}>{renderScreen()}</div>
        <StatusBar screen={screen} />
      </div>
      {paletteOpen && (
        <JumpPalette
          markets={pmData.markets}
          onSelect={jumpToMarket}
          onClose={() => setPaletteOpen(false)}
        />
      )}
      {runningStage && (
        <StageRunnerModal stage={runningStage} onClose={() => setRunningStage(null)} />
      )}
    </>
  )
}

const S: Record<string, CSSProperties> = {
  shell: {
    width: '100vw',
    height: '100vh',
    background: C.bg,
    color: C.text,
    fontFamily: F.body,
    fontSize: 13,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    fontFeatureSettings: '"tnum"'
  },
  topBar: {
    display: 'flex',
    alignItems: 'center',
    height: 46,
    padding: '0 18px',
    gap: 12,
    borderBottom: `1px solid ${C.line}`,
    background: C.bgPanel,
    position: 'relative',
    zIndex: 5,
    flexShrink: 0
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    paddingRight: 10,
    borderRight: `1px solid ${C.line}`
  },
  brandMark: {
    width: 24,
    height: 24,
    background: C.bgRaise,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: `1px solid ${C.line}`
  },
  brandText: {
    fontSize: 12.5,
    fontWeight: 700,
    fontFamily: F.display,
    letterSpacing: 0.3,
    color: C.text
  },
  brandVer: {
    fontSize: 9.5,
    fontFamily: F.mono,
    color: C.magenta,
    padding: '2px 5px',
    background: C.magentaSft,
    border: `1px solid ${C.magenta}`,
    letterSpacing: 0.5,
    fontWeight: 700
  },
  tabs: { display: 'flex', gap: 0, marginLeft: 4 },
  tab: {
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    color: C.textDim,
    padding: '14px 11px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 1,
    cursor: 'pointer',
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    outline: 'none'
  },
  tabActive: {
    color: C.magenta,
    borderBottom: `2px solid ${C.magenta}`,
    textShadow: `0 0 6px ${C.magenta}66`,
    background: C.magentaDim
  },
  tabBadge: {
    background: C.amber,
    color: C.bg,
    fontSize: 9,
    fontWeight: 700,
    padding: '1px 5px',
    letterSpacing: 0.4,
    boxShadow: `0 0 6px ${C.amber}88`
  },
  tabBadgeOn: {
    background: C.magenta,
    color: C.bg,
    fontSize: 9,
    fontWeight: 700,
    padding: '1px 5px',
    letterSpacing: 0.4,
    boxShadow: `0 0 6px ${C.magenta}88`
  },
  searchBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    background: C.bgInput,
    border: `1px solid ${C.line}`,
    padding: '5px 10px',
    width: 200,
    marginLeft: 'auto',
    cursor: 'pointer',
    outline: 'none'
  },
  kbd: {
    marginLeft: 'auto',
    fontSize: 9.5,
    fontFamily: F.mono,
    color: C.textMute,
    padding: '1px 5px',
    background: C.bg,
    border: `1px solid ${C.line}`,
    letterSpacing: 0.4
  },
  modeChip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '4px 10px',
    background: C.cyanSft,
    color: C.cyan,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 1,
    border: `1px solid ${C.cyan}`,
    fontFamily: F.mono,
    textShadow: `0 0 6px ${C.cyan}66`
  },
  modeChipDot: { width: 6, height: 6, background: C.cyan, boxShadow: `0 0 6px ${C.cyan}` },
  btnGhost: {
    background: 'transparent',
    border: `1px solid ${C.line}`,
    color: C.text,
    padding: '5px 11px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 0.6,
    cursor: 'pointer',
    textTransform: 'uppercase',
    outline: 'none'
  },
  btnPrimary: {
    background: C.magenta,
    color: C.bg,
    border: 'none',
    padding: '4px 14px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 0.8,
    cursor: 'pointer',
    textTransform: 'uppercase',
    boxShadow: `0 0 12px ${C.magenta}88`,
    outline: 'none',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: 1
  },
  btnPrimarySub: {
    fontSize: 8.5,
    fontWeight: 600,
    letterSpacing: 0.4,
    opacity: 0.8,
    textTransform: 'none'
  },
  body: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
    position: 'relative',
    zIndex: 1
  },
  statusBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 18,
    padding: '0 18px',
    height: 22,
    borderTop: `1px solid ${C.line}`,
    background: C.bgPanel,
    fontFamily: F.mono,
    fontSize: 10,
    color: C.textDim,
    letterSpacing: 0.4,
    position: 'relative',
    zIndex: 2,
    flexShrink: 0
  },
  paletteBackdrop: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.6)',
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'center',
    paddingTop: '14vh',
    zIndex: 120
  },
  paletteCard: {
    width: 560,
    maxWidth: '92vw',
    background: C.bgPanel,
    border: `1px solid ${C.lineHot}`,
    boxShadow: `0 0 24px ${C.magenta}44`
  },
  paletteInput: {
    width: '100%',
    background: C.bgInput,
    border: 'none',
    borderBottom: `1px solid ${C.line}`,
    color: C.text,
    fontFamily: F.mono,
    fontSize: 13,
    padding: '12px 14px',
    outline: 'none',
    boxSizing: 'border-box'
  },
  paletteList: { maxHeight: '46vh', overflowY: 'auto', padding: 6 },
  paletteEmpty: {
    fontFamily: F.mono,
    fontSize: 11.5,
    color: C.textMute,
    padding: '14px 10px'
  },
  paletteRow: {
    display: 'flex',
    alignItems: 'baseline',
    gap: 10,
    padding: '7px 10px',
    cursor: 'pointer',
    fontFamily: F.mono,
    fontSize: 12
  },
  paletteRowName: {
    flex: 1,
    color: C.textDim,
    fontFamily: F.body,
    fontSize: 11,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis'
  },
  paletteExpired: {
    fontSize: 9,
    color: C.textMute,
    border: `1px solid ${C.line}`,
    padding: '1px 5px',
    letterSpacing: 0.6
  }
}
