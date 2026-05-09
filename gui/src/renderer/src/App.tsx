import { useState, type CSSProperties } from 'react'
import { pmData } from './lib/pmData'
import { colors as C, fonts as F } from './styles/tokens'

type ScreenId = 'dashboard' | 'intake' | 'snapshots' | 'catalysts' | 'packet' | 'markets'

interface Tab {
  id: ScreenId
  label: string
  badge?: number
}

const pendingIntakeCount = (): number =>
  pmData.intake.filter((i) => i.status === 'suggested').length

const TopBar = ({
  screen,
  setScreen,
  onRunNextStage
}: {
  screen: ScreenId
  setScreen: (s: ScreenId) => void
  onRunNextStage: () => void
}) => {
  const tabs: Tab[] = [
    { id: 'dashboard', label: 'DASHBOARD' },
    { id: 'intake', label: 'INTAKE', badge: pendingIntakeCount() },
    { id: 'snapshots', label: 'SNAPSHOTS' },
    { id: 'catalysts', label: 'CATALYSTS' },
    { id: 'packet', label: 'PACKET' },
    { id: 'markets', label: 'MARKETS' }
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
      <div style={S.searchBar}>
        <span style={{ color: C.textMute }}>⌕</span>
        <span style={{ color: C.textMute, fontSize: 11 }}>jump to market…</span>
        <span style={S.kbd}>⌘K</span>
      </div>
      <div style={S.modeChip}>
        <span style={S.modeChipDot} />
        {pmData.liveState.mode}
      </div>
      <button style={S.btnGhost}>$ REFRESH</button>
      <button style={S.btnPrimary} onClick={onRunNextStage}>
        RUN NEXT STAGE ▸
      </button>
    </div>
  )
}

const StatusBar = ({ screen }: { screen: ScreenId }) => {
  const aging = pmData.freshness.filter((f) => f.state === 'aging')
  return (
    <div style={S.statusBar}>
      <span>● CONNECTED · 127.0.0.1:7777</span>
      <span style={{ color: C.cyan }}>● READ-ONLY</span>
      <span>
        SCREEN <span style={{ color: C.magenta }}>{screen.toUpperCase()}</span>
      </span>
      <span style={{ flex: 1 }} />
      <span>NET 4ms · LAST FETCH 13:42:11Z</span>
      {aging.length > 0 && (
        <span style={{ color: C.amber }}>
          ● {aging.length} ITEM{aging.length === 1 ? '' : 'S'} AGING
          {aging.length === 1 ? ` (${aging[0]!.file})` : ''}
        </span>
      )}
    </div>
  )
}

const ScreenStub = ({ name }: { name: string }) => (
  <div style={S.stub}>
    <div style={S.stubLabel}>{name}</div>
    <div style={S.stubHint}>screen not yet ported · step 2 placeholder</div>
  </div>
)

export const App = () => {
  const [screen, setScreen] = useState<ScreenId>('dashboard')

  const onRunNextStage = () => {
    if (pendingIntakeCount() > 0) {
      setScreen('intake')
    } else {
      alert('Advancing workflow → next CLI stage')
    }
  }

  return (
    <>
      <div style={S.shell}>
        <TopBar screen={screen} setScreen={setScreen} onRunNextStage={onRunNextStage} />
        <div style={S.body}>
          <ScreenStub name={screen.toUpperCase()} />
        </div>
        <StatusBar screen={screen} />
      </div>
      <div className="scanline-overlay" />
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
    marginLeft: 'auto'
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
    padding: '6px 14px',
    fontFamily: F.mono,
    fontSize: 10.5,
    fontWeight: 700,
    letterSpacing: 0.8,
    cursor: 'pointer',
    textTransform: 'uppercase',
    boxShadow: `0 0 12px ${C.magenta}88`,
    outline: 'none'
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
  stub: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10
  },
  stubLabel: {
    fontFamily: F.display,
    fontSize: 22,
    fontWeight: 700,
    letterSpacing: 0.5,
    color: C.magenta,
    textShadow: `0 0 14px ${C.magenta}55`
  },
  stubHint: {
    fontFamily: F.mono,
    fontSize: 10.5,
    letterSpacing: 1.2,
    color: C.textDim
  }
}
