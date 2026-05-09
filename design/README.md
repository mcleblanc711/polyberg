# Handoff: Polyberg Terminal

## Overview

A local desk GUI for a manual Polymarket research/trading workflow. The user keeps a markdown/yaml-based research repo (catalysts, snapshots, thesis, market registry, packet outputs) and runs CLI stages against it. The GUI is a **read-mostly window** onto that repo, plus a few **edit affordances** (intake, draft orders, catalyst editor).

**Read-only by default.** Nothing executes orders. The mode chip says `READ-ONLY`. Trade ticket "Draft Order" is the only state-change affordance, and it writes to `open_orders.yaml` for manual exec — never to an exchange.

## About the design files

The HTML/JSX in this bundle is a **design reference** — a working prototype that shows intended look, layout, and behavior. It's not production code to copy directly.

Your task is to **recreate this design in your target codebase's existing environment** (React/Next.js, Tauri, Electron, native, whatever) using its established patterns, component library, and state-management conventions. If no environment exists yet, pick the appropriate one — given this is a local desk app reading filesystem state, **Tauri** or **Electron** + React is a natural fit.

The design ships against fixture data on `window.pmData`. In the real app, swap that for filesystem reads (`fs.readFile` / Tauri `invoke`) of the user's research repo files.

## Fidelity

**High-fidelity.** Final colors, typography, spacing, and interactions are locked. Recreate pixel-perfect using the codebase's idiom — but the visual system itself (palette, type, density, glow, scanline overlay) is the design and should be preserved exactly.

## The visual system (cyberpunk-legible)

| token | value |
|---|---|
| `bg` | `#050007` |
| `bgPanel` | `#0c0009` |
| `bgRaise` | `#16010f` |
| `bgRow` | `#0a0008` |
| `bgInput` | `#0e0211` |
| `line` | `#2a0928` |
| `line2` | `#1a0512` |
| `lineHot` | `rgba(255,61,240,0.45)` |
| `text` | `#f0e8f5` |
| `textDim` | `#a08aa0` |
| `textMute` | `#7a5e7a` |
| `magenta` (primary) | `#ff3df0` |
| `magentaSft` | `rgba(255,61,240,0.14)` |
| `magentaDim` | `rgba(255,61,240,0.06)` |
| `cyan` (data/positive) | `#00ffd1` |
| `cyanSft` | `rgba(0,255,209,0.12)` |
| `amber` (warn) | `#ffb420` |
| `amberSft` | `rgba(255,180,32,0.14)` |
| `red` (negative) | `#ff3d6b` |
| `redSft` | `rgba(255,61,107,0.14)` |
| `yes` (chips) | `#00ffd1` |
| `no` (chips) | `#ff3d6b` |

### Typography

- **Display** (headings, position titles, brand): Space Grotesk 600, letter-spacing 0–1
- **Body** (rule text, catalyst entries, thesis): Inter 400/500
- **Mono** (numbers, prices, chips, labels, code blocks): JetBrains Mono 400/600/700, with `font-feature-settings: "tnum"` for numerics
- **All chips/labels/section headers are ALL CAPS** in mono with letter-spacing 0.4–1.5

Sizes: H1 18px, position title 16px, body 12.5–13px, chips 9.5–10.5px, big numbers 17–22px. Line-height 1.4–1.65.

### Effects

- **Clipped corners** on cards: top-right + bottom-left clipped 12px via `clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px))`
- **Scanline overlay** full-frame: `repeating-linear-gradient(0deg, transparent 0 2px, rgba(255,255,255,0.025) 2px 3px)`
- **Vignette overlay**: `radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%)`
- **Glow** via `text-shadow` and `drop-shadow()` filter on: mode chip, primary buttons, big P/L numbers, sparkline strokes, active tab labels, intake suggestion chip. Magenta glow `0 0 6–14px rgba(255,61,240,0.35–0.88)`. Cyan glow same pattern.
- **No chromatic aberration** anywhere on text. Numbers must be readable.
- **No emoji** in chrome. Icon glyphs only: `𝕏 ▤ ✎ ✓ ✕ ●`.

### Buttons

Two variants only — don't introduce a "filled secondary":

- **Ghost**: `background: transparent`, `border: 1px solid line`, `color: text`, mono caps. On hover, border + text shift to magenta.
- **Primary**: `background: magenta`, `color: bg`, `box-shadow: 0 0 12–14px rgba(255,61,240,0.88)`, mono caps.

## Frame

Fixed canvas **1480 × 1100**, scaled to fit any viewport via JS `transform: scale()` (see `shell.jsx` `Frame` component). Letterboxed on `#000`. Preserve this — at small viewports the GUI shrinks rather than reflows. If your target environment runs in a fixed-size window (Tauri/Electron), set the window to 1480×1100+ and skip the scaling.

## Screens

### 1. Top bar (always present)

| element | spec |
|---|---|
| Brand mark | 24×24 box, magenta SVG arrow glyph, magenta border |
| Brand text | "polyberg / terminal" Space Grotesk 700 12.5px |
| Version chip | "v0.4.1", magenta on magentaSft, mono 9.5px |
| Tabs | DASHBOARD / INTAKE / SNAPSHOTS / CATALYSTS / PACKET / MARKETS — mono caps 10.5px, active gets magenta + 2px underline + textShadow glow + bg magentaDim |
| Tab badge | Yellow square next to INTAKE showing pending suggestion count |
| Search bar | "⌕ jump to market…" + ⌘K kbd chip, fakeable for now |
| Mode chip | Cyan dot + "READ-ONLY", cyan glow |
| Refresh button | Ghost, "$ REFRESH" |
| Run next stage | Primary, "RUN NEXT STAGE ▸" |

### 2. Status bar (bottom, always present)

22px tall, mono 10px, `textDim`. Format: `● CONNECTED · 127.0.0.1:7777   ● READ-ONLY   SCREEN <name>   …   NET 4ms · LAST FETCH …Z   ● 1 ITEM AGING`

### 3. Dashboard

Three vertical bands stacked, then a 3-column body:

1. **MetricStrip** — 5 cells: EQUITY / DAY P/L / OPEN P/L / CASH / POSITIONS. Big mono numbers, optional cyan/red color + glow on signed values, hint text below.
2. **HeatStrip** — one cell per market showing the ID and 24h % change as a glowing chip, intensity-tinted background.
3. **3-col body**:
   - **WorkflowRail** (240px) — 6-step CLI ladder with state dots (✓/!/N), CLI command labels (`$ build-snapshot`), timestamps. "RUN NEXT STAGE" primary button. Below: context freshness list (file → age in min, dot color by freshness state). Below: sentiment box (Grok hook, currently NOT CONNECTED).
   - **Positions list** (flex) — section header + filter row + N PositionCards. Each card has a `posHead` (tags, market name, position/notional/P&L/sparkline + chevron) and an optional `ExpandedBody` when clicked. Only one card open at a time.
     - Tags: side (YES/NO), category, market id, open-orders count, rule-risk severity
     - ExpandedBody splits into 2 columns: left = price chart (13d) + bid/ask/spread/liq/snap-age, right = 5 tabs (RESOLUTION RULE / CATALYSTS / SNAPSHOT / OPEN ORDERS / DRAFT ORDER)
   - **RightRail** (290px) — 3 stacked cards: Active Thesis (with constraints list), Exposure (treemap + bars), Account (KV grid, read-only).

### 4. Intake

| section | spec |
|---|---|
| Header | "INTAKE / CONTEXT REBUILDER" + 4 stat blocks (LOADED / CONFIRMED / PENDING / REJECTED) |
| Paste panel | Kind selector (TWEET / ARTICLE / NOTE), author input, textarea (min 100px), live "SUGGESTED MARKET" chip with confidence %, CLEAR + ADD TO QUEUE buttons |
| Queue list | Each row: status dot (color by suggested/confirmed/rejected), kind icon glyph, author + timestamp + url, full text, suggested-market chip (clickable to retag via `<select>`), CONFIRM/REJECT/✕ actions |
| Footer | Warning line + "REBUILD CONTEXT · N CONFIRMED ▸" primary button |
| Rebuild modal | Magenta-bordered overlay, blurred backdrop. Body: per-market diff blocks showing proposed `recent_catalysts.md` appends as `+` lines; live_state and instructions sections show `=` no-change. Footer: WRITE & ADVANCE primary button. |

The auto-tag matcher in this prototype is a keyword check on `pmData.suggestMarket(text)`. In production, swap for an LLM call or proper embedding match.

### 5. Stub screens

These render real-looking content from the fixtures but their CRUD buttons are no-ops in the prototype. Wire them up the same way Intake works (form → diff modal → write to file).

- **Snapshots** — left: timeline table (TIMESTAMP / MARKETS / DIFFS / MISSING). Right: KV grid + diff vs previous. Selecting a row updates the right panel.
- **Catalysts** — left: market list with selection state. Right: per-catalyst rows (timestamp + source chip + text + EDIT/DEL buttons). + NEW CATALYST in header.
- **Packet** — 2 cols: packet.yaml on the left, adjudicator status on the right. Currently shows "AWAITING" state.
- **Markets** — registry table (MARKET ID / NAME / RULE-KEY / ORACLE / RESOLVES / RULE-RISK / MARK / EDIT).

## Interactions & behavior

- **Position card expand**: click `posHead` → toggles `expanded` state. Only one card open at a time. Magenta border + soft magenta box-shadow when active. Chevron rotates 180°.
- **Tab switching inside ExpandedBody**: click tab → state update. Active tab gets magenta color + 2px magenta underline + textShadow glow.
- **Run next stage**: if `pendingIntakeCount() > 0` → route to Intake screen + auto-open rebuild modal. Else → advance workflow stage (currently `alert()`).
- **Intake retag**: clicking a suggested-market chip swaps it for a `<select>` of all markets. Selection confirms the item.
- **Modal dismiss**: click overlay backdrop OR ✕ CANCEL. Don't dismiss on internal clicks (`stopPropagation`).
- **Snapshot row select**: click → `active` state updates → right panel re-renders.
- No animation framework. Use CSS `transition: all 0.15s` on cards. No spring physics.

## State management

This prototype uses local React state (`useState`). For the real app:

- **Per-screen UI state** (selected snapshot, expanded position, active tab, modal open) → component-local `useState` is fine.
- **Cross-screen domain state** (intake queue, live state, sentiment) → lift to a single store (Zustand / Jotai / Context) keyed by file. Treat each yaml/md file as a slice.
- **File watcher** → re-read source files on focus + on `chokidar` events. Debounce 300ms.
- **Optimistic writes** → for "WRITE & ADVANCE" and DRAFT ORDER, write to file then re-read to confirm. Show error state on write fail.
- **CLI invocation** → "RUN NEXT STAGE" should `spawn` the actual CLI tool (or Tauri command). Stream stdout/stderr to a log panel (consider adding one inside WorkflowRail).

## Design tokens

See visual system table above. To translate to a token system:
- Map all colors to a palette object
- Map type to 3 families × 4 weights
- Spacing follows 4/6/8/10/12/14/18/26 scale (irregular — used contextually, not as a strict ramp)
- No border radius (clip-path corners instead)
- Shadow tokens: glow-magenta-sm/md/lg, glow-cyan-sm/md/lg

## Assets

- **Fonts**: Inter, JetBrains Mono, Space Grotesk — all from Google Fonts (preconnect + display=swap)
- **Brand mark**: inline SVG (4 lines forming an upward arrow / spike). Replace in production with the user's actual logo.
- **No images** otherwise. All charts are inline SVG.

## Files in this bundle

| file | role |
|---|---|
| `Polyberg Terminal.html` | Entry point. Loads React/Babel, fonts, mounts AppShell. |
| `data.jsx` | Fixture data layer on `window.pmData`. Replace with filesystem reads. |
| `cyber.jsx` | Dashboard body — MetricStrip, HeatStrip, WorkflowRail, PositionCard + ExpandedBody (5 tabs), RightRail. Exports palette as `window.cyberC` and fonts as `window.cyberFonts`. |
| `shell.jsx` | AppShell — top bar + tab routing + status bar + scanline overlay + scale-to-fit Frame. |
| `intake.jsx` | IntakeScreen + RebuildModal. The most behaviorally complete screen. |
| `screens.jsx` | SnapshotsScreen / CatalystsScreen / PacketScreen / MarketsScreen — credible stubs. |
| `CONTEXT.md` | Project decisions, open threads, file conventions. Read this for the "why". |

## Visual reference

Screenshots of every screen at the locked 1480×1100 design size live in `screenshots/`:

| file | screen |
|---|---|
| `screenshots/01-dashboard.png` | Dashboard with the Hormuz position expanded — shows MetricStrip, HeatStrip, WorkflowRail, PositionCard + ExpandedBody with the price chart + RESOLUTION RULE tab, and the right rail (thesis, exposure treemap, account). |
| `screenshots/02-intake.png` | Intake screen — paste box, kind selector, queue rows with status dots and suggested-market chips, rebuild footer. |
| `screenshots/03-snapshots.png` | Snapshot history — timeline table on the left, KV grid + diff vs previous on the right. |
| `screenshots/04-catalysts.png` | Catalyst editor — market list on the left, per-catalyst rows on the right. |
| `screenshots/05-packet.png` | Packet review — packet.yaml on the left, adjudicator status on the right. |
| `screenshots/06-markets.png` | Market registry table. |

These are PNG captures at 1× — useful for confirming spacing, glow intensity, and color treatment when implementing.

## Reference reading order

1. `CONTEXT.md` — decisions and architecture overview
2. `Polyberg Terminal.html` — see how it all wires up
3. `data.jsx` — understand the data contract
4. `cyber.jsx` — see the visual system in action
5. `intake.jsx` — see the canonical "edit + diff + write" pattern, then apply it to the stub screens

## Open threads (to implement, in priority order)

1. **Wire CLI integration** — replace `pmData` with real filesystem reads + spawn CLI tools.
2. **File watcher** — re-read on focus + chokidar.
3. **Catalyst editor wiring** — make EDIT/DEL/+NEW round-trip to `recent_catalysts.md` (mirror Intake's diff-before-write).
4. **Markets registry editor** — full CRUD with rule-text editor + rule-risk note list.
5. **Packet adjudicator response** — design + build the response panel beyond "AWAITING".
6. **Snapshot diff** — derive from selected snapshot vs prior; currently hardcoded.
7. **Search (⌘K)** — fuzzy jump across markets / catalysts / order ids.
8. **Grok sentiment** — design connect flow + per-market sentiment surfacing. Hook reserved at `pmData.sentiment`.
9. **Persistence** — localStorage for intake queue + expanded position state during session.

## Notes for implementation

- Don't reflow the layout — the 1480×1100 fixed canvas is intentional. If your runtime is a window (Tauri/Electron), size the window accordingly.
- Don't introduce additional accent colors. Magenta + cyan + amber + red is the full palette.
- Don't replace the scanline overlay with a "more polished" alternative. The CRT feel is the design.
- Don't add light mode.
- The mode chip is load-bearing UX — it tells the user nothing executes. Keep it visible.
