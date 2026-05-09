// Direction: cyberpunk-legible.
// Hard contrast near-black, magenta + cyan accents, scanline overlay,
// clipped corners, mono-prevalent — but display face is Space Grotesk,
// no chromatic aberration on text. Numbers must be readable.
//
// Exports: window.CyberDashboardBody (rendered inside AppShell).
//          window.cyberC (palette) so other screens can match.

(function () {
  const D = window.pmData;
  const { useState } = React;

  const C = {
    bg:         '#050007',
    bgPanel:    '#0c0009',
    bgRaise:    '#16010f',
    bgRow:      '#0a0008',
    bgInput:    '#0e0211',
    line:       '#2a0928',
    line2:      '#1a0512',
    lineHot:    'rgba(255,61,240,0.45)',
    text:       '#f0e8f5',
    textDim:    '#a08aa0',
    textMute:   '#7a5e7a',
    magenta:    '#ff3df0',
    magentaSft: 'rgba(255,61,240,0.14)',
    magentaDim: 'rgba(255,61,240,0.06)',
    cyan:       '#00ffd1',
    cyanSft:    'rgba(0,255,209,0.12)',
    cyanDim:    'rgba(0,255,209,0.05)',
    amber:      '#ffb420',
    amberSft:   'rgba(255,180,32,0.14)',
    red:        '#ff3d6b',
    redSft:     'rgba(255,61,107,0.14)',
    yes:        '#00ffd1',
    no:         '#ff3d6b',
  };
  window.cyberC = C;

  const fontUI   = '"Inter","SF Pro Display",ui-sans-serif,system-ui,sans-serif';
  const fontMono = '"JetBrains Mono","SF Mono",ui-monospace,Menlo,monospace';
  const fontDisp = '"Space Grotesk","Inter",system-ui,sans-serif';
  window.cyberFonts = { fontUI, fontMono, fontDisp };

  // ---- visualization primitives ------------------------------------------

  function Spark({ data, w = 120, h = 32, color = C.cyan }) {
    const max = Math.max(...data), min = Math.min(...data);
    const dx = w / (data.length - 1);
    const y = v => h - ((v - min) / (max - min || 1)) * (h - 4) - 2;
    const path = data.map((v,i)=>`${i?'L':'M'}${(i*dx).toFixed(1)},${y(v).toFixed(1)}`).join('');
    const fill = `${path}L${w},${h}L0,${h}Z`;
    const id = 'spk_' + Math.random().toString(36).slice(2,7);
    return (
      <svg width={w} height={h} style={{ display: 'block', filter: `drop-shadow(0 0 3px ${color}88)` }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.4"/>
            <stop offset="100%" stopColor={color} stopOpacity="0"/>
          </linearGradient>
        </defs>
        <path d={fill} fill={`url(#${id})`}/>
        <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round"/>
      </svg>
    );
  }

  function PriceChart({ data, w, h }) {
    const pad = { l: 36, r: 14, t: 16, b: 24 };
    const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
    const max = Math.max(...data), min = Math.min(...data);
    const dx = iw / (data.length - 1);
    const y = v => pad.t + ih - ((v - min) / (max - min || 1)) * ih;
    const path = data.map((v,i)=>`${i?'L':'M'}${(pad.l+i*dx).toFixed(1)},${y(v).toFixed(1)}`).join('');
    const fill = `${path}L${(pad.l+(data.length-1)*dx).toFixed(1)},${pad.t+ih}L${pad.l},${pad.t+ih}Z`;
    const ticks = [min, (min+max)/2, max];
    return (
      <svg width={w} height={h} style={{ display: 'block' }}>
        <defs>
          <linearGradient id="pcfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.magenta} stopOpacity="0.32"/>
            <stop offset="100%" stopColor={C.magenta} stopOpacity="0"/>
          </linearGradient>
          <pattern id="pcgrid" width={iw/6} height={ih/4} patternUnits="userSpaceOnUse">
            <path d={`M ${iw/6} 0 L 0 0 0 ${ih/4}`} fill="none" stroke={C.line2} strokeWidth="0.5"/>
          </pattern>
        </defs>
        <rect x={pad.l} y={pad.t} width={iw} height={ih} fill="url(#pcgrid)"/>
        {ticks.map((t,i)=>(
          <g key={i}>
            <line x1={pad.l} x2={w-pad.r} y1={y(t)} y2={y(t)} stroke={C.line} strokeDasharray="2 6"/>
            <text x={pad.l-8} y={y(t)+3} textAnchor="end" fill={C.textMute} fontSize="10" fontFamily={fontMono}>{(t*100).toFixed(0)}¢</text>
          </g>
        ))}
        <path d={fill} fill="url(#pcfill)"/>
        <path d={path} fill="none" stroke={C.magenta} strokeWidth="2" strokeLinejoin="round"
              filter={`drop-shadow(0 0 4px ${C.magenta}99)`}/>
        <circle cx={pad.l+(data.length-1)*dx} cy={y(data.at(-1))} r="4" fill={C.magenta}/>
        <circle cx={pad.l+(data.length-1)*dx} cy={y(data.at(-1))} r="9" fill={C.magenta} opacity="0.25"/>
      </svg>
    );
  }
  window.cyberPriceChart = PriceChart;
  window.cyberSpark = Spark;

  function Treemap({ positions, w, h }) {
    const items = positions.map(p => {
      const m = D.marketById(p.marketId);
      return { ...p, m, notional: p.shares * p.mark, pnl: (p.mark - p.avg) * p.shares };
    });
    const total = items.reduce((a,i)=>a+i.notional,0);
    let x = 0;
    return (
      <svg width={w} height={h} style={{ display: 'block' }}>
        {items.map((it,i) => {
          const cw = (it.notional/total)*w;
          const accent = it.pnl >= 0 ? C.cyan : C.red;
          const fill = it.pnl >= 0 ? 'rgba(0,255,209,0.10)' : 'rgba(255,61,107,0.10)';
          const node = (
            <g key={i} transform={`translate(${x},0)`}>
              <rect width={cw-3} height={h} fill={fill} stroke={accent} strokeOpacity="0.5"/>
              <text x={10} y={18} fill={C.text} fontSize="11" fontWeight="600" fontFamily={fontDisp} letterSpacing="0.5">
                {it.m.id.split('_')[0].toUpperCase()}
              </text>
              <text x={10} y={32} fill={C.textDim} fontSize="9.5" fontFamily={fontMono} letterSpacing="0.4">
                {it.side} · {it.shares}
              </text>
              <text x={10} y={h-22} fill={accent} fontSize="13" fontFamily={fontMono} fontWeight="700">{D.fmtUsd(it.pnl, true)}</text>
              <text x={10} y={h-8} fill={C.textMute} fontSize="9.5" fontFamily={fontMono}>{((it.notional/total)*100).toFixed(0)}% · {D.fmtUsd(it.notional)}</text>
            </g>
          );
          x += cw;
          return node;
        })}
      </svg>
    );
  }

  // ---- top strips --------------------------------------------------------

  function MetricStrip() {
    const dayPos = D.dayPnl >= 0;
    return (
      <div style={S.metricStrip}>
        <BigMetric k="EQUITY"   v={D.fmtUsd(D.equity)}  hint="cash + open positions"/>
        <BigMetric k="DAY P/L"  v={D.fmtUsd(D.dayPnl, true)}  sub={D.fmtPct(D.dayPnl/D.equity*100, true)}  positive={dayPos}/>
        <BigMetric k="OPEN P/L" v={D.fmtUsd(D.totalPnl, true)} positive={D.totalPnl >= 0}  hint="vs avg cost"/>
        <BigMetric k="CASH"     v={D.fmtUsd(D.liveState.cash)} hint="available · USDC"/>
        <BigMetric k="POSITIONS"v={D.positions.length} hint={`${D.openOrders.length} open orders`}/>
      </div>
    );
  }

  function BigMetric({ k, v, sub, hint, positive }) {
    const color = positive == null ? C.text : positive ? C.cyan : C.red;
    const glow = positive == null ? 'none' : positive ? `0 0 12px rgba(0,255,209,0.35)` : `0 0 12px rgba(255,61,107,0.35)`;
    return (
      <div style={S.bigMetric}>
        <div style={S.bigMetricK}>{k}</div>
        <div style={{ ...S.bigMetricV, color, textShadow: glow }}>{v}</div>
        {sub ? <div style={{ ...S.bigMetricSub, color }}>{sub}</div> : null}
        {hint ? <div style={S.bigMetricHint}>{hint}</div> : null}
      </div>
    );
  }

  function HeatStrip() {
    return (
      <div style={S.heat}>
        {D.heat.map(h => {
          const intensity = Math.min(1, Math.abs(h.d) / 4);
          const accent = h.d >= 0 ? C.cyan : C.red;
          const glow = h.d >= 0 ? 'rgba(0,255,209,' : 'rgba(255,61,107,';
          const bg = `${glow}${0.04 + intensity*0.18})`;
          return (
            <div key={h.id} style={{ ...S.heatCell, background: bg, borderColor: `${glow}${0.2 + intensity*0.4})` }}>
              <div style={S.heatId}>{h.id.replace(/_/g,' ').slice(0,18)}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ ...S.heatVal, color: accent, textShadow: `0 0 8px ${accent}88` }}>{D.fmtPct(h.d, true)}</div>
                <svg width="32" height="12"><path d={`M0 ${h.d>=0?10:2} L32 ${h.d>=0?2:10}`} stroke={accent} strokeWidth="1.5"/></svg>
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  // ---- workflow rail (left) ----------------------------------------------

  function WorkflowRail({ onRunNextStage }) {
    return (
      <div style={S.wfRail}>
        <div style={S.railHdr}>// research workflow</div>
        <div style={S.wfStages}>
          {D.workflow.map((w, i) => {
            const c = w.state === 'ok' ? C.cyan : w.state === 'stale' ? C.amber : C.textMute;
            const last = i === D.workflow.length - 1;
            return (
              <div key={w.id} style={S.wfStage}>
                <div style={S.wfStageGlyph}>
                  <div style={{
                    ...S.wfStageDot,
                    borderColor: c,
                    background: w.state === 'ok' ? c : 'transparent',
                    color: w.state === 'ok' ? C.bg : c,
                    boxShadow: w.state === 'ok' ? `0 0 8px ${c}88` : 'none',
                  }}>
                    {w.state === 'ok' ? '✓' : w.state === 'stale' ? '!' : i+1}
                  </div>
                  {last ? null : <div style={{ ...S.wfStageLine, background: w.state === 'ok' ? c : C.line }}/>}
                </div>
                <div style={{ flex: 1, paddingBottom: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                    <div style={S.wfStageLabel}>{w.label}</div>
                    <div style={S.wfStageTs}>{w.ts}</div>
                  </div>
                  <div style={S.wfStageCli}>$ {w.cli}</div>
                </div>
              </div>
            );
          })}
        </div>
        <button style={S.btnPrimary} onClick={onRunNextStage}>RUN NEXT STAGE ▸</button>

        <div style={{ ...S.railHdr, marginTop: 18 }}>// context freshness</div>
        <div style={S.freshList}>
          {D.freshness.map(f => {
            const c = f.state === 'fresh' ? C.cyan : f.state === 'aging' ? C.amber : C.red;
            return (
              <div key={f.file} style={S.freshRow}>
                <div style={{ width: 6, height: 6, background: c, boxShadow: `0 0 6px ${c}` }}/>
                <div style={S.freshFile}>{f.file}</div>
                <div style={S.freshAge}>{f.age}m</div>
              </div>
            );
          })}
        </div>

        <div style={{ ...S.railHdr, marginTop: 18 }}>// sentiment · grok</div>
        <div style={S.sentBox}>
          <div style={S.sentRow}>
            <span style={S.sentLabel}>STATUS</span>
            <span style={{ ...S.sentVal, color: C.amber }}>NOT CONNECTED</span>
          </div>
          <div style={S.sentRow}>
            <span style={S.sentLabel}>SOURCE</span>
            <span style={S.sentVal}>{D.sentiment.source}</span>
          </div>
          <button style={S.btnGhost}>+ CONNECT GROK</button>
        </div>
      </div>
    );
  }

  // ---- positions list (center) -------------------------------------------

  function PositionCard({ p, expanded, onToggle }) {
    const m = D.marketById(p.marketId);
    const pnl = (p.mark - p.avg) * p.shares;
    const pnlPct = ((p.mark - p.avg) / p.avg) * 100;
    const totPos = pnl >= 0;
    const orders = D.openOrders.filter(o => o.marketId === m.id);
    const accent = totPos ? C.cyan : C.red;
    return (
      <div style={{
        ...S.posCard,
        borderColor: expanded ? C.magenta : C.line,
        boxShadow: expanded ? `0 0 0 1px ${C.magenta}, 0 0 20px rgba(255,61,240,0.18)` : 'none',
      }}>
        <div style={S.posHead} onClick={onToggle}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={S.posTags}>
              <span style={{
                ...S.tag,
                background: p.side === 'YES' ? C.cyanSft : C.redSft,
                color: p.side === 'YES' ? C.cyan : C.red,
                border: `1px solid ${p.side === 'YES' ? C.cyan : C.red}`,
              }}>{p.side}</span>
              <span style={{ ...S.tag, ...S.tagOutline, color: C.magenta, borderColor: C.magenta }}>{m.category.toUpperCase()}</span>
              <span style={{ ...S.tag, ...S.tagOutline, color: C.textDim, borderColor: C.line }}>{m.id}</span>
              {orders.length > 0 ? <span style={{ ...S.tag, ...S.tagOutline, color: C.cyan, borderColor: C.cyan }}>{orders.length} OPEN ORD</span> : null}
              <span style={{ ...S.tag, ...S.tagOutline, color: m.ruleRisk === 'high' ? C.red : m.ruleRisk === 'medium' ? C.amber : C.textDim, borderColor: m.ruleRisk === 'high' ? C.red : m.ruleRisk === 'medium' ? C.amber : C.line }}>RULE-RISK · {m.ruleRisk.toUpperCase()}</span>
            </div>
            <div style={S.posTitle}>{m.name}</div>
            <div style={S.posSub}>resolves {m.resolutionDate.split('T')[0]} · {m.oracle}</div>
          </div>

          <div style={S.posStatGroup}>
            <div style={S.statBlock}>
              <div style={S.statK}>POSITION</div>
              <div style={S.statV}>{p.shares.toLocaleString()}</div>
              <div style={S.statSub}>{(p.avg*100).toFixed(0)}¢ → {(p.mark*100).toFixed(0)}¢</div>
            </div>
            <div style={S.statBlock}>
              <div style={S.statK}>NOTIONAL</div>
              <div style={S.statV}>{D.fmtUsd(p.shares*p.mark)}</div>
              <div style={S.statSub}>{((p.shares*p.mark)/D.equity*100).toFixed(0)}% equity</div>
            </div>
            <div style={S.statBlock}>
              <div style={S.statK}>OPEN P/L</div>
              <div style={{ ...S.statV, color: accent, textShadow: `0 0 10px ${accent}66` }}>{D.fmtUsd(pnl, true)}</div>
              <div style={{ ...S.statSub, color: accent, opacity: 0.85 }}>{D.fmtPct(pnlPct, true)}</div>
            </div>
            <div style={{ ...S.statBlock, alignItems: 'flex-end' }}>
              <div style={S.statK}>TREND · 13d</div>
              <Spark data={m.hist} w={120} h={30} color={accent}/>
            </div>
            <div style={{ ...S.chev, transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>▾</div>
          </div>
        </div>
        {expanded ? <ExpandedBody m={m} p={p}/> : null}
      </div>
    );
  }

  function ExpandedBody({ m, p }) {
    const [tab, setTab] = useState('rules');
    const orders = D.openOrders.filter(o => o.marketId === m.id);
    const tabs = [
      ['rules',     'RESOLUTION RULE'],
      ['catalysts', 'CATALYSTS'],
      ['snapshot',  'SNAPSHOT'],
      ['orders',    `OPEN ORDERS · ${orders.length}`],
      ['draft',     'DRAFT ORDER'],
    ];
    return (
      <div style={S.expanded}>
        <div style={S.expGrid}>
          <div style={S.expPanel}>
            <div style={S.expPanelHdr}>
              <span>// price · 13d</span>
              <span style={{ color: C.magenta, fontFamily: fontMono, fontSize: 12, textShadow: `0 0 6px ${C.magenta}88` }}>{(m.mark*100).toFixed(1)}¢ · LIVE</span>
            </div>
            <PriceChart data={m.hist} w={500} h={170}/>
            <div style={S.miniGrid}>
              <Mini k="BID"      v={(m.bid*100).toFixed(1)+'¢'} accent={C.cyan}/>
              <Mini k="ASK"      v={(m.ask*100).toFixed(1)+'¢'} accent={C.red}/>
              <Mini k="SPREAD"   v={m.spread+'¢'}/>
              <Mini k="LIQ"      v={D.fmtUsd(m.liq)}/>
              <Mini k="SNAP"     v={m.snapshotAge+'m old'}/>
            </div>
          </div>

          <div style={S.expPanel}>
            <div style={S.tabRow}>
              {tabs.map(([id, label]) => (
                <button key={id} onClick={() => setTab(id)}
                  style={{ ...S.tab, ...(tab === id ? S.tabActive : null) }}>{label}</button>
              ))}
            </div>
            <div style={S.tabBody}>
              {tab === 'rules'     ? <RulesPane m={m}/> : null}
              {tab === 'catalysts' ? <CatalystsPane m={m}/> : null}
              {tab === 'snapshot'  ? <SnapshotPane m={m}/> : null}
              {tab === 'orders'    ? <OrdersPane m={m}/> : null}
              {tab === 'draft'     ? <DraftPane m={m} p={p}/> : null}
            </div>
          </div>
        </div>
      </div>
    );
  }

  function Mini({ k, v, accent }) {
    return (
      <div style={S.mini}>
        <div style={S.miniK}>{k}</div>
        <div style={{ ...S.miniV, color: accent || C.text }}>{v}</div>
      </div>
    );
  }

  function RulesPane({ m }) {
    return (
      <div>
        <p style={S.ruleText}>{m.ruleText}</p>
        <div style={S.subhdr}>// rule-risk notes</div>
        {m.ruleRiskNotes.map((n, i) => (
          <div key={i} style={S.callout}>
            <div style={S.calloutBar}/>
            <div style={S.calloutText}>{n}</div>
          </div>
        ))}
      </div>
    );
  }

  function CatalystsPane({ m }) {
    return (
      <div>
        <div style={S.subhdr}>// recent_catalysts.md · last 72h</div>
        <div style={{ position: 'relative', paddingLeft: 16, marginLeft: 4 }}>
          <div style={{ position: 'absolute', left: 4, top: 8, bottom: 8, width: 1, background: C.line }}/>
          {m.catalysts.map((c, i) => (
            <div key={i} style={S.tlRow}>
              <div style={S.tlDot}/>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ color: C.magenta, fontFamily: fontMono, fontSize: 11, letterSpacing: 0.3 }}>{c.t}</span>
                  <span style={{ ...S.tag, ...S.tagOutline, color: C.cyan, borderColor: C.cyan, fontSize: 9.5 }}>{c.src}</span>
                </div>
                <div style={S.tlText}>{c.txt}</div>
              </div>
            </div>
          ))}
        </div>
        <button style={{ ...S.btnGhost, marginTop: 10 }}>+ ADD CATALYST</button>
      </div>
    );
  }

  function SnapshotPane({ m }) {
    return (
      <div>
        <div style={S.subhdr}>// snapshots/2026-05-08T13-24Z.json</div>
        <div style={S.snapGrid}>
          <SnapKV k="MARK"        v={m.mark.toFixed(3)}/>
          <SnapKV k="BID / ASK"   v={`${m.bid.toFixed(3)} / ${m.ask.toFixed(3)}`}/>
          <SnapKV k="SPREAD"      v={m.spread+' ¢'}/>
          <SnapKV k="LIQUIDITY"   v={D.fmtUsd(m.liq)}/>
          <SnapKV k="SNAP AGE"    v={m.snapshotAge+' min'}/>
          <SnapKV k="ORACLE"      v={m.oracle}/>
        </div>
        <div style={S.subhdr}>// diff vs previous</div>
        <div style={S.diffBlock}>
          <div style={S.diffLine}><span style={S.diffPlus}>+</span><span>mark · {m.hist.at(-3).toFixed(3)} → {m.mark.toFixed(3)} <span style={{ color: C.cyan }}>(+{((m.mark-m.hist.at(-3))*100).toFixed(1)}¢)</span></span></div>
          <div style={S.diffLine}><span style={S.diffEq}>=</span><span>spread · {m.spread} ¢ <span style={{ color: C.textMute }}>no change</span></span></div>
          <div style={S.diffLine}><span style={S.diffPlus}>+</span><span>liquidity · <span style={{ color: C.cyan }}>+$2,140</span></span></div>
          <div style={S.diffLine}><span style={S.diffEq}>=</span><span>missing-info · <span style={{ color: C.cyan }}>clean</span></span></div>
        </div>
      </div>
    );
  }

  function SnapKV({ k, v }) {
    return (
      <div style={S.snapCell}>
        <div style={S.miniK}>{k}</div>
        <div style={{ ...S.miniV, fontSize: 14 }}>{v}</div>
      </div>
    );
  }

  function OrdersPane({ m }) {
    const orders = D.openOrders.filter(o => o.marketId === m.id);
    return (
      <div>
        <div style={S.subhdr}>// open_orders.yaml · {orders.length} working · LIMIT only</div>
        {orders.map(o => (
          <div key={o.id} style={S.ordCard}>
            <div style={{ ...S.tag, background: o.kind === 'BUY' ? C.cyanSft : C.redSft, color: o.kind === 'BUY' ? C.cyan : C.red, border: `1px solid ${o.kind === 'BUY' ? C.cyan : C.red}` }}>{o.kind}</div>
            <div style={{ flex: 1 }}>
              <div style={S.ordTitle}>{o.kind === 'BUY' ? 'Buy' : 'Sell'} {o.qty} {o.side} @ {(o.px*100).toFixed(1)}¢</div>
              <div style={S.ordSub}>id <span style={{ color: C.magenta }}>{o.id}</span> · placed {o.placed.replace('T',' ').slice(0,16)}Z · {D.fmtUsd(o.px*o.qty)} notional</div>
            </div>
            <div style={S.ordStatus}>● {o.status}</div>
          </div>
        ))}
      </div>
    );
  }

  function DraftPane({ m, p }) {
    return (
      <div>
        <div style={S.subhdr}>// draft → open_orders.yaml · no execution</div>
        <div style={S.draftGrid}>
          <DfField k="MARKET" v={m.id} accent={C.magenta}/>
          <DfField k="SIDE" v="YES" accent={C.cyan}/>
          <DfField k="KIND" v="BUY · LIMIT"/>
          <DfField k="PRICE" v="0.74¢"/>
          <DfField k="QUANTITY" v="500"/>
          <DfField k="NOTIONAL" v={D.fmtUsd(0.74*500)}/>
        </div>
        <div style={S.subhdr}>// yaml preview</div>
        <pre style={S.codeBlock}>{
`- id: o-9201
  market_id: ${m.id}
  side: YES
  kind: BUY
  px: 0.74
  qty: 500
  status: DRAFT
  human_review_required: true`}</pre>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, alignItems: 'center' }}>
          <button style={S.btnPrimary}>WRITE TO open_orders.yaml ▸</button>
          <button style={S.btnGhost}>DISCARD</button>
          <span style={{ flex: 1 }}/>
          <span style={{ fontSize: 10.5, color: C.amber, fontFamily: fontMono, letterSpacing: 0.5, textShadow: `0 0 6px ${C.amber}66` }}>● NO ORDER PLACED · MANUAL EXEC</span>
        </div>
      </div>
    );
  }

  function DfField({ k, v, accent }) {
    return (
      <div style={S.dfField}>
        <div style={S.dfK}>{k}</div>
        <div style={{ ...S.dfV, color: accent || C.text }}>{v}</div>
      </div>
    );
  }

  // ---- right rail --------------------------------------------------------

  function RightRail() {
    return (
      <div style={S.rightRail}>
        <div style={S.rrCard}>
          <div style={S.rrHdr}>// active thesis</div>
          <div style={S.thesisText}>{D.liveState.thesis}</div>
          <div style={S.constraintsHdr}>// constraints</div>
          {D.liveState.constraints.map((c, i) => (
            <div key={i} style={S.constraint}>
              <span style={{ color: C.magenta, marginRight: 6, textShadow: `0 0 4px ${C.magenta}` }}>›</span>{c}
            </div>
          ))}
        </div>

        <div style={S.rrCard}>
          <div style={S.rrHdr}>// exposure</div>
          <div style={{ padding: 10 }}>
            <Treemap positions={D.positions} w={266} h={108}/>
          </div>
          <div style={{ padding: '0 12px 12px' }}>
            <ExposureBars/>
          </div>
        </div>

        <div style={S.rrCard}>
          <div style={S.rrHdr}>// account · read-only</div>
          <div style={{ padding: '4px 12px 12px' }}>
            <KVRow k="proxy wallet"  v="0xA3…f2D1" mono/>
            <KVRow k="positions"     v="3 imported · 0 diffs"/>
            <KVRow k="open orders"   v={`${D.openOrders.length} imported`}/>
            <KVRow k="last fetch"    v="13:42:11 UTC" mono/>
            <KVRow k="mode"          v="GET only" accent={C.cyan}/>
            <button style={{ ...S.btnGhost, marginTop: 8, width: '100%' }}>$ import-account-snapshot</button>
          </div>
        </div>
      </div>
    );
  }

  function KVRow({ k, v, mono, accent }) {
    return (
      <div style={S.kvRow}>
        <span style={S.kvK}>{k}</span>
        <span style={{ ...S.kvV, fontFamily: mono ? fontMono : fontUI, color: accent || C.text }}>{v}</span>
      </div>
    );
  }

  function ExposureBars() {
    const total = D.positions.reduce((a,p)=>a+p.shares*p.mark,0);
    const byCat = {};
    D.positions.forEach(p => {
      const cat = D.marketById(p.marketId).category;
      byCat[cat] = (byCat[cat]||0) + p.shares*p.mark;
    });
    return (
      <>
        {Object.entries(byCat).map(([cat, n]) => {
          const pct = (n/total)*100;
          return (
            <div key={cat} style={{ marginBottom: 6 }}>
              <div style={{ display: 'flex', fontSize: 10.5, color: C.textDim, marginBottom: 3 }}>
                <span style={{ flex: 1, letterSpacing: 0.5 }}>{cat.toUpperCase()}</span>
                <span style={{ fontFamily: fontMono, color: C.text }}>{D.fmtUsd(n)} · {pct.toFixed(0)}%</span>
              </div>
              <div style={{ height: 5, background: C.line2 }}>
                <div style={{ width: pct+'%', height: '100%', background: `linear-gradient(90deg, ${C.magenta}, ${C.cyan})`, boxShadow: `0 0 6px ${C.magenta}66` }}/>
              </div>
            </div>
          );
        })}
        <div style={S.cap}>
          <span style={{ color: C.cyan }}>✓</span>
          <span>SINGLE-MKT CAP 30% · MAX <span style={{ color: C.text, fontFamily: fontMono }}>{(Math.max(...Object.values(byCat))/total*100).toFixed(0)}%</span></span>
        </div>
      </>
    );
  }

  // ---- entry point: dashboard body --------------------------------------

  function CyberDashboardBody({ onRunNextStage }) {
    const [expanded, setExpanded] = useState('hormuz_normal_may15');
    return (
      <>
        <MetricStrip/>
        <HeatStrip/>
        <div style={S.body}>
          <WorkflowRail onRunNextStage={onRunNextStage}/>
          <div style={S.main}>
            <div style={S.sectionHdr}>
              <div>
                <div style={S.sectionTitle}>POSITIONS</div>
                <div style={S.sectionSub}>{D.positions.length} positions · click any to expand</div>
              </div>
              <div style={S.filterRow}>
                <button style={S.filterBtnOn}>ALL</button>
                <button style={S.filterBtn}>YES</button>
                <button style={S.filterBtn}>NO</button>
                <span style={{ width: 12 }}/>
                <button style={S.filterBtn}>NOTIONAL ↓</button>
              </div>
            </div>
            {D.positions.map(p => (
              <PositionCard key={p.marketId} p={p}
                expanded={expanded === p.marketId}
                onToggle={() => setExpanded(expanded === p.marketId ? null : p.marketId)}/>
            ))}
          </div>
          <RightRail/>
        </div>
      </>
    );
  }

  // ---- styles -----------------------------------------------------------

  const clipCard = 'polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px))';

  const S = {
    body: { flex: 1, display: 'flex', minHeight: 0 },

    metricStrip: { display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', borderBottom: `1px solid ${C.line}`, background: C.bgPanel },
    bigMetric: { padding: '12px 18px', borderRight: `1px solid ${C.line}` },
    bigMetricK: { fontSize: 10, color: C.textDim, letterSpacing: 1.5, fontWeight: 600, fontFamily: fontMono },
    bigMetricV: { fontSize: 22, fontWeight: 700, fontFamily: fontMono, marginTop: 4, letterSpacing: -0.5 },
    bigMetricSub: { fontSize: 11, fontFamily: fontMono, marginTop: 2, fontWeight: 600 },
    bigMetricHint: { fontSize: 10, color: C.textMute, marginTop: 2, letterSpacing: 0.4 },

    heat: { display: 'flex', gap: 5, padding: '8px 20px', borderBottom: `1px solid ${C.line}`, background: C.bg },
    heatCell: { flex: 1, display: 'flex', flexDirection: 'column', gap: 3, padding: '6px 10px', border: `1px solid` },
    heatId: { fontSize: 9.5, color: C.textDim, fontFamily: fontMono, letterSpacing: 0.5, textTransform: 'uppercase' },
    heatVal: { fontSize: 12, fontWeight: 700, fontFamily: fontMono, letterSpacing: 0.4 },

    wfRail: { width: 240, borderRight: `1px solid ${C.line}`, padding: 14, background: C.bg, overflow: 'auto' },
    railHdr: { fontSize: 10, color: C.magenta, letterSpacing: 1.5, fontWeight: 600, marginBottom: 10, fontFamily: fontMono, textShadow: `0 0 6px ${C.magenta}66` },
    wfStages: { paddingLeft: 4 },
    wfStage: { display: 'flex', gap: 10 },
    wfStageGlyph: { display: 'flex', flexDirection: 'column', alignItems: 'center', flex: '0 0 22px' },
    wfStageDot: { width: 20, height: 20, border: '1.5px solid', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, fontFamily: fontMono },
    wfStageLine: { width: 1.5, flex: 1, marginTop: 2 },
    wfStageLabel: { fontSize: 11.5, fontWeight: 600, fontFamily: fontDisp, letterSpacing: 0.2 },
    wfStageTs: { fontSize: 9.5, color: C.textMute, fontFamily: fontMono, marginLeft: 'auto' },
    wfStageCli: { fontSize: 10.5, color: C.cyan, fontFamily: fontMono, marginTop: 2, letterSpacing: 0.3 },

    btnGhost: { background: 'transparent', border: `1px solid ${C.line}`, color: C.text, padding: '7px 12px', fontFamily: fontMono, fontSize: 10.5, fontWeight: 600, letterSpacing: 0.6, cursor: 'pointer', textTransform: 'uppercase', width: 'auto', marginTop: 6 },
    btnPrimary: { background: C.magenta, color: C.bg, border: 'none', padding: '8px 14px', fontFamily: fontMono, fontSize: 11, fontWeight: 700, letterSpacing: 0.8, cursor: 'pointer', textTransform: 'uppercase', boxShadow: `0 0 14px ${C.magenta}88, 0 0 0 1px ${C.magenta}`, width: '100%', marginTop: 4 },

    freshList: { background: C.bgPanel, border: `1px solid ${C.line}`, padding: 6 },
    freshRow: { display: 'flex', alignItems: 'center', gap: 8, padding: '4px 4px', fontSize: 10.5 },
    freshFile: { flex: 1, color: C.text, fontFamily: fontMono, fontSize: 10.5 },
    freshAge: { color: C.textDim, fontFamily: fontMono },

    sentBox: { background: C.bgPanel, border: `1px solid ${C.line}`, padding: 8 },
    sentRow: { display: 'flex', justifyContent: 'space-between', padding: '3px 0', fontSize: 10.5, fontFamily: fontMono },
    sentLabel: { color: C.textDim, letterSpacing: 0.6 },
    sentVal: { color: C.text, letterSpacing: 0.4 },

    main: { flex: 1, padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0, overflow: 'auto' },
    sectionHdr: { display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', padding: '0 0 4px' },
    sectionTitle: { fontSize: 18, fontWeight: 700, letterSpacing: 1, fontFamily: fontDisp, color: C.text },
    sectionSub: { fontSize: 11, color: C.textDim, marginTop: 2, fontFamily: fontMono },
    filterRow: { display: 'flex', gap: 4, alignItems: 'center' },
    filterBtn: { background: 'transparent', border: `1px solid ${C.line}`, color: C.textDim, padding: '4px 10px', fontSize: 10.5, fontFamily: fontMono, letterSpacing: 0.6, cursor: 'pointer', textTransform: 'uppercase' },
    filterBtnOn: { background: C.magentaSft, border: `1px solid ${C.magenta}`, color: C.magenta, padding: '4px 10px', fontSize: 10.5, fontFamily: fontMono, letterSpacing: 0.6, cursor: 'pointer', fontWeight: 700, textShadow: `0 0 6px ${C.magenta}66`, textTransform: 'uppercase' },

    posCard: { background: C.bgPanel, border: '1px solid', clipPath: clipCard, transition: 'all 0.15s' },
    posHead: { padding: '14px 16px', cursor: 'pointer' },
    posTags: { display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' },
    tag: { padding: '2px 8px', fontSize: 9.5, fontWeight: 700, letterSpacing: 0.8, fontFamily: fontMono, textTransform: 'uppercase' },
    tagOutline: { background: 'transparent', border: '1px solid' },
    posTitle: { fontSize: 16, fontWeight: 600, lineHeight: 1.35, fontFamily: fontDisp, color: C.text, letterSpacing: -0.1 },
    posSub: { fontSize: 11, color: C.textDim, marginTop: 3, fontFamily: fontMono, letterSpacing: 0.3 },
    posStatGroup: { display: 'flex', gap: 26, alignItems: 'center', marginTop: 12 },
    statBlock: { display: 'flex', flexDirection: 'column', gap: 2 },
    statK: { fontSize: 9.5, color: C.textDim, letterSpacing: 1, fontWeight: 600, fontFamily: fontMono },
    statV: { fontSize: 17, fontFamily: fontMono, fontWeight: 700, letterSpacing: -0.3, lineHeight: 1.2 },
    statSub: { fontSize: 10.5, color: C.textMute, fontFamily: fontMono, letterSpacing: 0.3 },
    chev: { color: C.magenta, fontSize: 16, transition: 'transform 0.2s', marginLeft: 4, textShadow: `0 0 6px ${C.magenta}` },

    expanded: { borderTop: `1px solid ${C.line}`, padding: 14, background: C.bgRow },
    expGrid: { display: 'grid', gridTemplateColumns: '540px 1fr', gap: 12 },
    expPanel: { background: C.bgPanel, border: `1px solid ${C.line}`, padding: 14 },
    expPanelHdr: { display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: C.textDim, letterSpacing: 0.6, marginBottom: 10, fontWeight: 600, fontFamily: fontMono },

    miniGrid: { display: 'flex', gap: 0, marginTop: 14, paddingTop: 12, borderTop: `1px solid ${C.line2}` },
    mini: { flex: 1, paddingRight: 10, borderRight: `1px solid ${C.line2}` },
    miniK: { fontSize: 9.5, color: C.textDim, letterSpacing: 1, fontFamily: fontMono, fontWeight: 600 },
    miniV: { fontSize: 13, fontFamily: fontMono, marginTop: 3, fontWeight: 600 },

    tabRow: { display: 'flex', gap: 0, marginBottom: 12, borderBottom: `1px solid ${C.line}` },
    tab: { background: 'transparent', border: 'none', borderBottom: '2px solid transparent', color: C.textDim, padding: '6px 10px', fontFamily: fontMono, fontSize: 10.5, fontWeight: 600, cursor: 'pointer', letterSpacing: 0.6 },
    tabActive: { color: C.magenta, borderBottom: `2px solid ${C.magenta}`, textShadow: `0 0 6px ${C.magenta}66` },
    tabBody: { fontSize: 12.5, lineHeight: 1.55 },

    ruleText: { fontSize: 12.5, lineHeight: 1.65, color: C.text, margin: 0, padding: '8px 0', borderTop: `1px solid ${C.line2}`, borderBottom: `1px solid ${C.line2}`, fontFamily: fontUI },
    subhdr: { fontSize: 10, color: C.magenta, letterSpacing: 0.8, fontWeight: 600, margin: '12px 0 8px', fontFamily: fontMono, textShadow: `0 0 4px ${C.magenta}66` },

    callout: { display: 'flex', gap: 10, padding: '6px 12px', background: C.amberSft, marginBottom: 5, alignItems: 'flex-start', borderLeft: `2px solid ${C.amber}` },
    calloutBar: { display: 'none' },
    calloutText: { fontSize: 12, lineHeight: 1.45, flex: 1, color: C.text },

    tlRow: { display: 'flex', gap: 12, paddingBottom: 12, position: 'relative' },
    tlDot: { position: 'absolute', left: -16, top: 6, width: 9, height: 9, background: C.magenta, boxShadow: `0 0 0 3px ${C.magentaSft}, 0 0 0 4px ${C.bgPanel}, 0 0 8px ${C.magenta}` },
    tlText: { fontSize: 12.5, color: C.text, marginTop: 4, lineHeight: 1.5, fontFamily: fontUI },

    snapGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 6 },
    snapCell: { background: C.bgRow, border: `1px solid ${C.line2}`, padding: '6px 10px' },
    diffBlock: { background: C.bgRow, border: `1px solid ${C.line2}`, padding: 12, fontFamily: fontMono, fontSize: 12 },
    diffLine: { display: 'flex', gap: 10, padding: '3px 0' },
    diffPlus: { color: C.cyan, width: 14 },
    diffEq: { color: C.textMute, width: 14 },

    ordCard: { display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', background: C.bgRow, border: `1px solid ${C.line2}`, marginBottom: 5 },
    ordTitle: { fontSize: 12.5, fontFamily: fontMono, color: C.text },
    ordSub: { fontSize: 10.5, color: C.textDim, fontFamily: fontMono, marginTop: 2, letterSpacing: 0.3 },
    ordStatus: { fontSize: 10.5, color: C.amber, fontFamily: fontMono, letterSpacing: 0.6, textShadow: `0 0 6px ${C.amber}66` },

    draftGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 4 },
    dfField: { background: C.bgRow, border: `1px solid ${C.line2}`, padding: '8px 12px' },
    dfK: { fontSize: 9.5, color: C.textDim, letterSpacing: 1, fontFamily: fontMono, fontWeight: 600 },
    dfV: { fontSize: 14, fontFamily: fontMono, marginTop: 4, fontWeight: 700 },
    codeBlock: { background: C.bg, border: `1px solid ${C.line2}`, padding: 12, fontSize: 11.5, color: C.cyan, fontFamily: fontMono, lineHeight: 1.6, margin: 0, whiteSpace: 'pre-wrap' },

    rightRail: { width: 290, borderLeft: `1px solid ${C.line}`, padding: 14, display: 'flex', flexDirection: 'column', gap: 12, background: C.bg, overflow: 'auto' },
    rrCard: { background: C.bgPanel, border: `1px solid ${C.line}`, clipPath: clipCard },
    rrHdr: { padding: '10px 12px 6px', fontSize: 10, color: C.magenta, letterSpacing: 0.8, fontWeight: 600, fontFamily: fontMono, textShadow: `0 0 4px ${C.magenta}66` },
    thesisText: { fontSize: 12, lineHeight: 1.55, padding: '0 12px', color: C.text, fontFamily: fontUI },
    constraintsHdr: { fontSize: 10, color: C.magenta, letterSpacing: 0.8, fontWeight: 600, marginTop: 10, padding: '0 12px', fontFamily: fontMono, textShadow: `0 0 4px ${C.magenta}66` },
    constraint: { fontSize: 11.5, padding: '3px 12px', color: C.text, lineHeight: 1.4, fontFamily: fontUI },

    cap: { fontSize: 10, color: C.textDim, marginTop: 8, paddingTop: 8, borderTop: `1px dashed ${C.line}`, display: 'flex', gap: 6, fontFamily: fontMono, letterSpacing: 0.5 },

    kvRow: { display: 'flex', padding: '3px 0', fontSize: 11 },
    kvK: { flex: 1, color: C.textDim, fontFamily: fontMono, letterSpacing: 0.4 },
    kvV: { color: C.text, fontSize: 11 },
  };

  window.CyberDashboardBody = CyberDashboardBody;
})();
