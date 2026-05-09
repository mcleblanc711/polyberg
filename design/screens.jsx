// Stub screens for snapshot history, catalyst editor, packet review,
// market registry. Each is a credible placeholder built from existing
// pmData fixtures — they look real but full editing is wired only on
// the dashboard + intake for now.

(function () {
  const D = window.pmData;
  const C = window.cyberC;
  const F = window.cyberFonts;
  const { useState } = React;

  const sx = {
    root: { flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, padding: 18, gap: 14, overflow: 'auto' },
    h1: { fontSize: 18, fontWeight: 700, fontFamily: F.fontDisp, letterSpacing: 1, color: C.text },
    h1Sub: { fontSize: 11, color: C.textDim, fontFamily: F.fontMono, marginTop: 3, letterSpacing: 0.4 },
    panel: { background: C.bgPanel, border: `1px solid ${C.line}`, padding: 14 },
    panelHdr: { fontSize: 10, color: C.magenta, letterSpacing: 0.8, fontWeight: 700, fontFamily: F.fontMono, marginBottom: 10, textShadow: `0 0 4px ${C.magenta}66`, display: 'flex', alignItems: 'center', gap: 14 },
    table: { width: '100%', borderCollapse: 'collapse', fontSize: 11.5, fontFamily: F.fontMono },
    th: { textAlign: 'left', padding: '8px 10px', color: C.textDim, fontSize: 9.5, letterSpacing: 1, fontWeight: 700, borderBottom: `1px solid ${C.line}` },
    td: { padding: '8px 10px', borderBottom: `1px solid ${C.line2}`, color: C.text },
    rowHover: { cursor: 'pointer' },
    chip: { padding: '2px 7px', border: '1px solid', fontSize: 9.5, fontFamily: F.fontMono, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase' },
    btnGhost: { background: 'transparent', border: `1px solid ${C.line}`, color: C.text, padding: '4px 10px', fontFamily: F.fontMono, fontSize: 10, fontWeight: 700, letterSpacing: 0.6, cursor: 'pointer', textTransform: 'uppercase' },
    code: { background: C.bgRow, border: `1px solid ${C.line2}`, padding: 12, fontFamily: F.fontMono, fontSize: 11.5, color: C.cyan, lineHeight: 1.65, margin: 0, whiteSpace: 'pre-wrap' },
  };

  function Header({ title, sub, right }) {
    return (
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <div style={sx.h1}>{title}</div>
          <div style={sx.h1Sub}>{sub}</div>
        </div>
        {right}
      </div>
    );
  }

  // ============== SNAPSHOTS ==============
  function SnapshotsScreen() {
    const [active, setActive] = useState(D.snapshots[0].ts);
    const cur = D.snapshots.find(s => s.ts === active);
    return (
      <div style={sx.root}>
        <Header title="SNAPSHOT HISTORY" sub="// snapshots/ · click row for KV grid + diff vs previous"/>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, flex: 1, minHeight: 0 }}>
          <div style={{ ...sx.panel, overflow: 'auto' }}>
            <div style={sx.panelHdr}>// timeline · {D.snapshots.length} captures</div>
            <table style={sx.table}>
              <thead><tr>
                <th style={sx.th}>TIMESTAMP</th><th style={sx.th}>MARKETS</th>
                <th style={sx.th}>DIFFS</th><th style={sx.th}>MISSING</th>
              </tr></thead>
              <tbody>
                {D.snapshots.map(s => {
                  const on = s.ts === active;
                  return (
                    <tr key={s.ts} onClick={() => setActive(s.ts)}
                        style={{ ...sx.rowHover, background: on ? C.magentaDim : 'transparent' }}>
                      <td style={{ ...sx.td, color: on ? C.magenta : C.text, fontWeight: on ? 700 : 400 }}>{s.ts}</td>
                      <td style={sx.td}>{s.markets}</td>
                      <td style={{ ...sx.td, color: s.diffsCount > 3 ? C.amber : C.cyan }}>{s.diffsCount}</td>
                      <td style={{ ...sx.td, color: s.missingInfo > 0 ? C.red : C.textMute }}>{s.missingInfo}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div style={{ ...sx.panel, overflow: 'auto' }}>
            <div style={sx.panelHdr}>// {cur.file}</div>
            <pre style={sx.code}>{`{
  "ts":            "${cur.ts}",
  "markets":       ${cur.markets},
  "diffs":         ${cur.diffsCount},
  "missing_info":  ${cur.missingInfo},
  "generated_by":  "build-snapshot v0.4.1",
  "fresh_minutes": ${cur.freshMin}
}`}</pre>
            <div style={{ ...sx.panelHdr, marginTop: 14 }}>// diff vs previous capture</div>
            <pre style={sx.code}>{`+ hormuz_normal_may15 · mark 0.76 → 0.78  (+2.0¢)
+ hormuz_normal_may15 · liq +$2,140
= cl_high_120_end_june · no change
- trump_blockade_lifted_apr30 · mark 0.44 → 0.42  (-2.0¢)
+ trump_blockade_lifted_apr30 · spread 3¢ → 4¢   widen`}</pre>
          </div>
        </div>
      </div>
    );
  }
  window.SnapshotsScreen = SnapshotsScreen;

  // ============== CATALYSTS ==============
  function CatalystsScreen() {
    const [mid, setMid] = useState(D.markets[0].id);
    const m = D.marketById(mid);
    return (
      <div style={sx.root}>
        <Header title="CATALYST EDITOR" sub="// recent_catalysts.md · per-market timeline · edit / delete / add"
          right={<button style={sx.btnGhost}>+ NEW CATALYST</button>}/>
        <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 12, flex: 1, minHeight: 0 }}>
          <div style={{ ...sx.panel, overflow: 'auto' }}>
            <div style={sx.panelHdr}>// markets</div>
            {D.markets.map(mm => {
              const on = mm.id === mid;
              return (
                <div key={mm.id} onClick={() => setMid(mm.id)}
                  style={{ padding: '10px 10px', cursor: 'pointer', borderLeft: '2px solid', borderColor: on ? C.magenta : 'transparent', background: on ? C.magentaDim : 'transparent', marginBottom: 4 }}>
                  <div style={{ fontSize: 11.5, fontFamily: F.fontDisp, fontWeight: on ? 700 : 500, color: on ? C.magenta : C.text }}>{mm.id}</div>
                  <div style={{ fontSize: 10, color: C.textDim, fontFamily: F.fontMono, marginTop: 2 }}>{mm.catalysts.length} entries</div>
                </div>
              );
            })}
          </div>
          <div style={{ ...sx.panel, overflow: 'auto' }}>
            <div style={sx.panelHdr}>// {m.id} · {m.catalysts.length} catalysts</div>
            {m.catalysts.map((c, i) => (
              <div key={i} style={{ display: 'flex', gap: 12, padding: '10px 0', borderBottom: `1px solid ${C.line2}` }}>
                <div style={{ minWidth: 140 }}>
                  <div style={{ color: C.magenta, fontFamily: F.fontMono, fontSize: 10.5, letterSpacing: 0.4, textShadow: `0 0 4px ${C.magenta}66` }}>{c.t}</div>
                  <div style={{ ...sx.chip, color: C.cyan, borderColor: C.cyan, display: 'inline-block', marginTop: 4 }}>{c.src}</div>
                </div>
                <div style={{ flex: 1, fontSize: 12.5, color: C.text, lineHeight: 1.5, fontFamily: F.fontUI }}>{c.txt}</div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button style={sx.btnGhost}>EDIT</button>
                  <button style={{ ...sx.btnGhost, color: C.red, borderColor: C.line }}>DEL</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }
  window.CatalystsScreen = CatalystsScreen;

  // ============== PACKET ==============
  function PacketScreen() {
    return (
      <div style={sx.root}>
        <Header title="PACKET REVIEW" sub="// build-packet output → adjudicator input → trade ticket"/>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, flex: 1, minHeight: 0 }}>
          <div style={{ ...sx.panel, overflow: 'auto' }}>
            <div style={sx.panelHdr}>// packet.yaml · last build 13:00Z</div>
            <pre style={sx.code}>{`packet:
  generated:    2026-05-08T13:00:00Z
  freshness:    PASS  (all imports < 60min)
  markets:      3
  positions:    3
  open_orders:  4
  thesis:       "Hormuz status-quo bias persists…"
  constraints:
    - single_market_max_pct: 30
    - min_days_to_resolution: 7
  attachments:
    - portfolio_current.yaml
    - open_orders.yaml
    - recent_catalysts.md
    - snapshots/2026-05-08T13-24Z.json`}</pre>
          </div>
          <div style={{ ...sx.panel, overflow: 'auto' }}>
            <div style={sx.panelHdr}>// adjudicator response · pending</div>
            <pre style={{ ...sx.code, color: C.amber }}>{`status:        AWAITING
last_validate: 13:21Z  (pass)
last_input:    adjudicator_input.yaml  (47KB)
next_action:   $ validate-adjudicator
              → build-trade-ticket`}</pre>
            <div style={{ ...sx.panelHdr, marginTop: 14 }}>// proposed actions · 0 ready</div>
            <div style={{ padding: 16, color: C.textMute, fontFamily: F.fontMono, fontSize: 11.5, textAlign: 'center', border: `1px dashed ${C.line}` }}>
              waiting for adjudicator validation · run next stage to proceed
            </div>
          </div>
        </div>
      </div>
    );
  }
  window.PacketScreen = PacketScreen;

  // ============== MARKETS ==============
  function MarketsScreen() {
    return (
      <div style={sx.root}>
        <Header title="MARKET REGISTRY" sub="// market_registry.yaml · 3 tracked · read/write"
          right={<button style={sx.btnGhost}>+ ADD MARKET</button>}/>
        <div style={{ ...sx.panel, overflow: 'auto', flex: 1 }}>
          <table style={sx.table}>
            <thead><tr>
              <th style={sx.th}>MARKET ID</th>
              <th style={sx.th}>NAME</th>
              <th style={sx.th}>RULE-KEY</th>
              <th style={sx.th}>ORACLE</th>
              <th style={sx.th}>RESOLVES</th>
              <th style={sx.th}>RULE-RISK</th>
              <th style={sx.th}>MARK</th>
              <th style={sx.th}/>
            </tr></thead>
            <tbody>
              {D.markets.map(m => (
                <tr key={m.id}>
                  <td style={{ ...sx.td, color: C.magenta, fontWeight: 700 }}>{m.id}</td>
                  <td style={{ ...sx.td, fontFamily: F.fontUI, maxWidth: 320 }}>{m.name}</td>
                  <td style={sx.td}>{m.ruleKey}</td>
                  <td style={sx.td}>{m.oracle}</td>
                  <td style={sx.td}>{m.resolutionDate.split('T')[0]}</td>
                  <td style={sx.td}>
                    <span style={{ ...sx.chip, color: m.ruleRisk === 'high' ? C.red : m.ruleRisk === 'medium' ? C.amber : C.textDim, borderColor: m.ruleRisk === 'high' ? C.red : m.ruleRisk === 'medium' ? C.amber : C.line }}>{m.ruleRisk}</span>
                  </td>
                  <td style={{ ...sx.td, color: C.cyan }}>{(m.mark*100).toFixed(1)}¢</td>
                  <td style={sx.td}><button style={sx.btnGhost}>EDIT</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }
  window.MarketsScreen = MarketsScreen;
})();
