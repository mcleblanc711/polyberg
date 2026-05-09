# Polyberg — Context Dump

_Snapshot of decisions, architecture, and open threads. Update as project evolves._

---

## What this is

A **local desk GUI** for a manual Polymarket research/trading workflow. The user keeps a markdown/yaml-based research repo (catalysts, snapshots, thesis, market registry, packet outputs) and runs CLI stages against it. The GUI is a **read-mostly window** onto that repo, plus a few **edit affordances** (intake, draft orders, catalyst editor). Nothing executes orders — every "write" is to a yaml/md file the user reviews before running.

Read-only by default. The mode chip says `READ-ONLY` / `GET only`. Trade ticket draft is the only thing that proposes a state change, and it writes to `open_orders.yaml` for manual exec — never to an exchange.

---

## Decisions (locked)

### Aesthetic direction
**Cyberpunk-legible.** Picked from the A/B/C exploration in `Cyberpunk options.html`.
- Near-black background with magenta tint (`#050007` / `#0c0009`)
- Magenta primary (`#ff3df0`), cyan data/positive (`#00ffd1`), amber warn (`#ffb420`), red negative (`#ff3d6b`)
- **Space Grotesk** display, **Inter** body, **JetBrains Mono** numerics — no Major Mono Display
- **No chromatic aberration on text.** Numbers must be readable.
- Clipped corners on cards (top-right + bottom-left, 12px polygon)
- Subtle scanlines + vignette as a full-frame overlay (z-index 10, pointer-events none)
- Glow on key elements only (mode chip, primary buttons, big P/L numbers, sparkline strokes) via `text-shadow` + `drop-shadow` filters

### Workflow vocabulary
The user thinks in **CLI stages** chained against files:
- `import-account-snapshot` → `portfolio_current.yaml`, `open_orders.yaml`
- `build-snapshot` → `snapshots/<ts>.json`
- `build-catalysts` → `recent_catalysts.md`
- `build-packet` → `packet.yaml`
- `validate-adjudicator` → adjudicator output
- `build-trade-ticket` → draft `open_orders.yaml` entry

WorkflowRail in the dashboard reflects these as a 6-step ladder with state (`ok`/`stale`/`pending`) and last-run timestamps. "RUN NEXT STAGE" advances; if there are pending intake items it routes to the Intake screen first.

### UX patterns
- **Expand-row** for positions (only one open at a time). Inside: 5 tabs — Resolution Rule, Catalysts, Snapshot, Open Orders, Draft Order.
- **Top tabs** for screen routing (not a left nav) — saves vertical space at 1480×1100.
- **Auto-tag with override** in Intake — suggested market chip is clickable to edit; rejection is one click.
- **Diff before write** — Intake's "rebuild" opens a modal showing proposed appends to `recent_catalysts.md` per market before any file write.

### Frame
Fixed 1480×1100, scaled to fit any viewport via JS `transform: scale()` in `shell.jsx`. Letterboxed on `#000`. Status bar at the bottom shows connection state + screen + last fetch.

---

## File architecture

```
data.jsx                      Fixture data + helpers (pmData on window)
                              - markets, positions, openOrders, snapshots
                              - workflow stages, freshness, intake queue
                              - liveState (cash, equity, thesis, constraints, mode)
                              - sentiment stub (Grok hook reserved)
                              - heat[], dayPnl, totalPnl
                              - fmtUsd, fmtPct, marketById, suggestMarket

cyber.jsx                     Dashboard body (CyberDashboardBody)
                              - MetricStrip, HeatStrip, WorkflowRail
                              - PositionCard + ExpandedBody (tabs)
                              - RightRail (thesis, exposure treemap, account)
                              - Spark + PriceChart + Treemap (also exposed
                                on window for other screens to reuse)
                              - Exports cyberC palette + cyberFonts

shell.jsx                     AppShell (top bar, screen routing, status bar,
                              overlay, scale-to-fit Frame)
                              - Tabs: dashboard / intake / snapshots /
                                catalysts / packet / markets
                              - "Run next stage" routes to Intake if pending

intake.jsx                    IntakeScreen + RebuildModal
                              - Paste box (tweet/article/note + author)
                              - Live suggested-market chip with confidence
                              - Queue with confirm/reject/retag/remove
                              - Rebuild diff modal (per-market appends)

screens.jsx                   Stubs for the other 4 tabs:
                              - SnapshotsScreen — timeline + KV grid + diff
                              - CatalystsScreen — per-market editor
                              - PacketScreen — yaml + adjudicator state
                              - MarketsScreen — registry table

Polyberg Terminal.html      Mounts AppShell. Loads Inter/JetBrains/
                              Space Grotesk from Google Fonts.

Polyberg Terminal v1.html   Backup — three-direction comparison
                              (Terminal · Amber · Arc) on a design canvas.

Cyberpunk options.html        Backup — A/B/C cyberpunk intensity comparison
                              that led to the current direction.
```

### Loading order
React → ReactDOM → Babel → data.jsx → cyber.jsx → intake.jsx → screens.jsx → shell.jsx → mount script. Mount script polls until all globals are present.

### Data layer contracts
Anything new should hang off `window.pmData`. Keys other screens already consume:
- `pmData.markets` (id, name, category, ruleKey, oracle, ruleText, ruleRiskNotes[], ruleRisk, mark, bid, ask, spread, liq, hist[], catalysts[], snapshotAge, resolutionDate)
- `pmData.positions` (marketId, side, shares, avg, mark, openedAt)
- `pmData.openOrders` (id, marketId, side, kind, px, qty, status, placed)
- `pmData.snapshots`, `pmData.workflow`, `pmData.freshness`
- `pmData.intake` (id, kind, addedAt, author, text, suggestedMarket, suggestionConfidence, status)
- `pmData.liveState` (cash, equity, mode, thesis, constraints[])
- `pmData.sentiment` (source: 'grok', status: 'not_connected', samples[]) — reserved
- `pmData.suggestMarket(text)` — keyword matcher used by intake

---

## What's wired vs stubbed

**Wired (interactive):**
- Dashboard expand/collapse, all 5 tabs inside a position
- Intake: paste, kind toggle, auto-suggest, confirm/reject/retag/remove, rebuild diff modal (renders real diff text from queue state)
- Top-bar tab routing
- "Run next stage" → routes to Intake if pending suggestions

**Stubbed (look real, no edits):**
- Snapshots screen — selectable rows, but the JSON/diff is hardcoded for the active row
- Catalysts editor — list renders, EDIT/DEL buttons are no-ops
- Packet screen — yaml is static
- Markets registry — table renders, EDIT is a no-op
- Search bar (⌘K), Refresh button — no-ops
- Grok sentiment — `pmData.sentiment` reserved, panel says NOT CONNECTED

---

## Open threads / next obvious moves

1. **Grok sentiment** — design the connect flow + the inline panel that surfaces sentiment scores per market. Hook is in `pmData.sentiment`.
2. **Catalyst editor** — wire EDIT/DELETE/+NEW so it round-trips to `recent_catalysts.md` (mirrors Intake's diff-before-write).
3. **Packet screen** — design the adjudicator response panel (status, validate flow, derived trade tickets).
4. **Markets registry editor** — full CRUD with rule-text editor + rule-risk note list.
5. **Snapshot diff polish** — currently hardcoded; should derive from selected snapshot vs prior.
6. **Search (⌘K)** — fuzzy jump across markets / catalysts / order ids.
7. **Tweaks panel** — palette swaps (rose/lime/cyan variants), density toggle, scanline intensity, "calm mode" that softens glow.
8. **Persistence** — none currently; user state evaporates on reload. Consider localStorage for intake queue + expanded position.

---

## Things deliberately NOT done

- No real network. Everything is fixture data on `pmData`.
- No emoji in chrome (icon glyphs only: `𝕏 ▤ ✎ ✓ ✕ ●`).
- No left nav (top tabs only).
- No chromatic aberration anywhere.
- No bottom-pinned terminal log (was an option in early Terminal direction; user picked Cyberpunk-legible without it).
- No light mode. No.

---

## File-write conventions

When adding screens or features:
- New screens go in `screens.jsx` (or split out if they grow). Export to `window.<Name>Screen` and add a tab in `shell.jsx`.
- Reuse `cyberC` palette + `cyberFonts` from `window` — don't reintroduce colors.
- Reuse `cyberSpark` / `cyberPriceChart` for any new chart so glow/grid stays consistent.
- All chips/labels are ALL CAPS with letter-spacing in JetBrains Mono. Body copy is Inter. Numbers/prices are JetBrains Mono with `font-feature-settings: "tnum"`.
- New buttons: ghost (`border, transparent bg, magenta-text on hover`) or primary (`magenta bg + glow`). No filled secondary.
- Card chrome: `clipPath: clipCard` with magenta border on hover/active; `bgPanel` fill.
