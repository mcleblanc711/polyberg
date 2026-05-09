// AppShell — owns top bar + screen routing.
// Mounts at #root, renders the selected screen inside a 1480x1100 frame
// scaled to fit any viewport (letterboxed on bg).
//
// Screens it routes to (all globals on window):
//   CyberDashboardBody, IntakeScreen, SnapshotsScreen,
//   CatalystsScreen, PacketScreen, MarketsScreen

(function () {
  const D = window.pmData;
  const C = window.cyberC;
  const F = window.cyberFonts;
  const { useState, useEffect, useRef } = React;

  // pending intake items count → drives the badge on the Intake tab
  function pendingIntakeCount() {
    return D.intake.filter(i => i.status === 'suggested').length;
  }

  function TopBar({ screen, setScreen, onRunNextStage }) {
    const tabs = [
      ['dashboard',  'DASHBOARD'],
      ['intake',     'INTAKE',     pendingIntakeCount()],
      ['snapshots',  'SNAPSHOTS'],
      ['catalysts',  'CATALYSTS'],
      ['packet',     'PACKET'],
      ['markets',    'MARKETS'],
    ];
    return (
      <div style={S.topBar}>
        <div style={S.brand}>
          <div style={S.brandMark}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path d="M4 18 L4 6 L12 12 L20 6 L20 18" stroke={C.magenta} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" filter={`drop-shadow(0 0 3px ${C.magenta})`}/>
            </svg>
          </div>
          <div style={S.brandText}>polyberg / terminal</div>
          <div style={S.brandVer}>v0.4.1</div>
        </div>

        <div style={S.tabs}>
          {tabs.map(([id, label, badge]) => {
            const on = screen === id;
            return (
              <button key={id} onClick={() => setScreen(id)} style={{ ...S.tab, ...(on ? S.tabActive : null) }}>
                {label}
                {badge ? <span style={on ? S.tabBadgeOn : S.tabBadge}>{badge}</span> : null}
              </button>
            );
          })}
        </div>

        <div style={S.searchBar}>
          <span style={{ color: C.textMute }}>⌕</span>
          <span style={{ color: C.textMute, fontSize: 11 }}>jump to market…</span>
          <span style={S.kbd}>⌘K</span>
        </div>
        <div style={S.modeChip}>
          <span style={{ width: 6, height: 6, background: C.cyan, boxShadow: `0 0 6px ${C.cyan}` }}/>
          {D.liveState.mode}
        </div>
        <button style={S.btnGhost}>$ REFRESH</button>
        <button style={S.btnPrimary} onClick={onRunNextStage}>RUN NEXT STAGE ▸</button>
      </div>
    );
  }

  function StatusBar({ screen }) {
    return (
      <div style={S.statusBar}>
        <span>● CONNECTED · 127.0.0.1:7777</span>
        <span style={{ color: C.cyan }}>● READ-ONLY</span>
        <span>SCREEN <span style={{ color: C.magenta }}>{screen.toUpperCase()}</span></span>
        <span style={{ flex: 1 }}/>
        <span>NET 4ms · LAST FETCH 13:42:11Z</span>
        <span style={{ color: C.amber }}>● 1 ITEM AGING (recent_catalysts.md)</span>
      </div>
    );
  }

  // Scanline + vignette overlay applied to the whole frame.
  function Overlay() {
    return (
      <div style={S.overlay} aria-hidden="true">
        <div style={S.scanlines}/>
        <div style={S.vignette}/>
      </div>
    );
  }

  function AppShell() {
    const [screen, setScreen] = useState('dashboard');
    const [showRebuild, setShowRebuild] = useState(false);
    const onRunNextStage = () => {
      if (pendingIntakeCount() > 0) {
        // hand off to intake screen — user must approve queue first
        setScreen('intake');
        setTimeout(() => setShowRebuild(true), 60);
      } else {
        // advance workflow stage (stub)
        alert('Advancing workflow → next CLI stage');
      }
    };

    let body;
    if (screen === 'dashboard')      body = <window.CyberDashboardBody onRunNextStage={onRunNextStage}/>;
    else if (screen === 'intake')    body = <window.IntakeScreen showRebuild={showRebuild} setShowRebuild={setShowRebuild}/>;
    else if (screen === 'snapshots') body = <window.SnapshotsScreen/>;
    else if (screen === 'catalysts') body = <window.CatalystsScreen/>;
    else if (screen === 'packet')    body = <window.PacketScreen/>;
    else if (screen === 'markets')   body = <window.MarketsScreen/>;

    return (
      <Frame>
        <TopBar screen={screen} setScreen={setScreen} onRunNextStage={onRunNextStage}/>
        <div style={S.bodyWrap}>{body}</div>
        <StatusBar screen={screen}/>
        <Overlay/>
      </Frame>
    );
  }

  // Fixed 1480x1100 frame, letterboxed via JS scale-to-fit.
  function Frame({ children }) {
    const ref = useRef(null);
    useEffect(() => {
      const fit = () => {
        const el = ref.current; if (!el) return;
        const sx = window.innerWidth / 1480;
        const sy = window.innerHeight / 1100;
        const s = Math.min(sx, sy, 1);
        el.style.transform = `translate(-50%,-50%) scale(${s})`;
      };
      fit();
      window.addEventListener('resize', fit);
      return () => window.removeEventListener('resize', fit);
    }, []);
    return (
      <div style={S.stage}>
        <div ref={ref} style={S.frame}>{children}</div>
      </div>
    );
  }

  const S = {
    stage: { position: 'fixed', inset: 0, background: '#000', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' },
    frame: { width: 1480, height: 1100, background: C.bg, color: C.text, fontFamily: F.fontUI, fontSize: 13, display: 'flex', flexDirection: 'column', position: 'absolute', top: '50%', left: '50%', transformOrigin: 'center center', boxShadow: `0 0 40px rgba(255,61,240,0.15), 0 0 0 1px ${C.line}`, fontFeatureSettings: '"tnum","ss01"', overflow: 'hidden' },

    overlay: { position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 10 },
    scanlines: { position: 'absolute', inset: 0, background: 'repeating-linear-gradient(0deg, transparent 0, transparent 2px, rgba(255,255,255,0.025) 2px, rgba(255,255,255,0.025) 3px)' },
    vignette: { position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%)' },

    topBar: { display: 'flex', alignItems: 'center', height: 46, padding: '0 18px', gap: 12, borderBottom: `1px solid ${C.line}`, background: C.bgPanel, position: 'relative', zIndex: 5 },
    brand: { display: 'flex', alignItems: 'center', gap: 8, paddingRight: 10, borderRight: `1px solid ${C.line}` },
    brandMark: { width: 24, height: 24, background: C.bgRaise, display: 'flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${C.line}` },
    brandText: { fontSize: 12.5, fontWeight: 700, fontFamily: F.fontDisp, letterSpacing: 0.3, color: C.text },
    brandVer: { fontSize: 9.5, fontFamily: F.fontMono, color: C.magenta, padding: '2px 5px', background: C.magentaSft, border: `1px solid ${C.magenta}`, letterSpacing: 0.5, fontWeight: 700 },

    tabs: { display: 'flex', gap: 0, marginLeft: 4 },
    tab: { background: 'transparent', border: 'none', borderBottom: '2px solid transparent', color: C.textDim, padding: '14px 11px', fontFamily: F.fontMono, fontSize: 10.5, fontWeight: 700, letterSpacing: 1, cursor: 'pointer', position: 'relative', display: 'flex', alignItems: 'center', gap: 6 },
    tabActive: { color: C.magenta, borderBottom: `2px solid ${C.magenta}`, textShadow: `0 0 6px ${C.magenta}66`, background: C.magentaDim },
    tabBadge: { background: C.amber, color: C.bg, fontSize: 9, fontWeight: 700, padding: '1px 5px', letterSpacing: 0.4, boxShadow: `0 0 6px ${C.amber}88` },
    tabBadgeOn: { background: C.magenta, color: C.bg, fontSize: 9, fontWeight: 700, padding: '1px 5px', letterSpacing: 0.4, boxShadow: `0 0 6px ${C.magenta}88` },

    searchBar: { display: 'flex', alignItems: 'center', gap: 8, background: C.bgInput, border: `1px solid ${C.line}`, padding: '5px 10px', width: 200, marginLeft: 'auto' },
    kbd: { marginLeft: 'auto', fontSize: 9.5, fontFamily: F.fontMono, color: C.textMute, padding: '1px 5px', background: C.bg, border: `1px solid ${C.line}`, letterSpacing: 0.4 },

    modeChip: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', background: C.cyanSft, color: C.cyan, fontSize: 10.5, fontWeight: 700, letterSpacing: 1, border: `1px solid ${C.cyan}`, fontFamily: F.fontMono, textShadow: `0 0 6px ${C.cyan}66` },

    btnGhost: { background: 'transparent', border: `1px solid ${C.line}`, color: C.text, padding: '5px 11px', fontFamily: F.fontMono, fontSize: 10.5, fontWeight: 700, letterSpacing: 0.6, cursor: 'pointer', textTransform: 'uppercase' },
    btnPrimary: { background: C.magenta, color: C.bg, border: 'none', padding: '6px 14px', fontFamily: F.fontMono, fontSize: 10.5, fontWeight: 700, letterSpacing: 0.8, cursor: 'pointer', textTransform: 'uppercase', boxShadow: `0 0 12px ${C.magenta}88` },

    bodyWrap: { flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, position: 'relative', zIndex: 1 },

    statusBar: { display: 'flex', alignItems: 'center', gap: 18, padding: '0 18px', height: 22, borderTop: `1px solid ${C.line}`, background: C.bgPanel, fontFamily: F.fontMono, fontSize: 10, color: C.textDim, letterSpacing: 0.4, position: 'relative', zIndex: 2 },
  };

  window.AppShell = AppShell;
})();
