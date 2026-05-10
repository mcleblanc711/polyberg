# Polyberg Project Summary

Last reviewed: 2026-05-10

## Purpose

Polyberg is a local-first Python research workbench for structured Polymarket analysis. It
turns manually maintained market, portfolio, order, catalyst, and rule context into repeatable
markdown packets for LLM review, validates model/adjudicator JSON against strict schemas, and
renders a human trade ticket from validated adjudicator output.

The project is intentionally not an automated trading system. Its safety posture is that every
model recommendation is untrusted until validated, and every final order still requires manual
human review and manual execution outside this repo.

A read-mostly GUI ("Polyberg Terminal") is being built on top of the CLI in `gui/`.

## GUI (Polyberg Terminal)

Local Electron app that renders the existing yaml/md research repo and shells out to the CLI
for stage advancement. Read-mostly; the only state-change affordance is a draft-order panel
that writes to `open_orders.yaml` for manual exec — nothing executes orders.

### Stack

- **electron-vite** + **React 18** + **TypeScript** under `gui/`.
- Hardened BrowserWindow: `sandbox: true`, `contextIsolation: true`, `nodeIntegration: false`,
  `autoHideMenuBar: true`. Min size 1200×800, default 1480×1100.
- Three TS configs: root references node + web. `npm run typecheck && npm run build` is the
  smoke test.
- Linux dev requires the Chromium sandbox helper to be setuid root after every `npm install`
  that re-extracts Electron:
  `sudo chown root:root gui/node_modules/electron/dist/chrome-sandbox && sudo chmod 4755 …`

### Strategy: visual-first, IPC last (path B)

The plan deliberately ports the visual layer against typed fixture data first, then swaps the
data source to a real `window.pm` IPC bridge as the last step. The bundled `pmData` shape in
`gui/src/renderer/src/lib/pmData.ts` mirrors the prototype's `window.pmData` exactly, so the
final swap is one substitution rather than a rewrite. Tauri is the planned upgrade if polyberg
becomes more serious; Electron was chosen now for Chromium-perfect rendering of the locked
visual system.

### What's ported

- **Skeleton** (`commit 17a469a`) — 1480×1100 hardened window, palette/font tokens, vignette
  overlay, Google Fonts. The repeating-linear-gradient scanline was dropped in `259b817`
  because it read as visual noise rather than CRT atmosphere; the radial vignette stays and
  the `.scanline-overlay` class name was kept so `App.tsx` did not need to change.
- **Fixtures** (`commit 096bacc`) — `lib/types.ts` + `lib/format.ts` + `lib/pmData.ts`. Bundled
  `PmData` object plus individual exports.
- **AppShell** (`commit a8fe00d`) — top bar (brand, version, six tabs, search placeholder,
  mode chip, refresh, run-next-stage), tab routing, status bar with derived aging count.
  Routing was simplified to an exhaustive switch in `89a2eb5` once every tab had a real
  screen.
- **Dashboard** (`commit 61ec881`) — six modules under `screens/dashboard/`: charts.tsx
  (Spark, PriceChart, Treemap), Strips.tsx (Metric + Heat), WorkflowRail, PositionCard
  (with 5-tab ExpandedBody), RightRail, DashboardScreen entry.
- **Markets** (`commit f781f06`) — `screens/markets/MarketsScreen.tsx`. Registry table with
  rule-key, oracle, resolution date, severity-colored rule-risk chip, and current mark in
  cents. `+ ADD MARKET` and `EDIT` are cosmetic ghosts.
- **Packet** (`commit 1c3bfe5`) — `screens/packet/PacketScreen.tsx`. Two-pane: packet.yaml
  block on the left, adjudicator status (amber) plus dashed "waiting" placeholder for
  proposed-actions on the right. Hardcoded text mirrors the prototype.
- **Catalysts** (`commit 1bb1c95`) — `screens/catalysts/CatalystsScreen.tsx`. 260px market
  list on the left, per-market catalyst timeline on the right with timestamp + cyan source
  chip, body text, and ghost EDIT/DEL.
- **Snapshots** (`commit 13b5d5d`) — `screens/snapshots/SnapshotsScreen.tsx`. Clickable
  timeline table on the left (diffs amber/cyan by threshold, missing-info red when
  nonzero), KV-grid JSON view + verbatim diff-vs-previous block on the right keyed off the
  selected row.
- **Intake** (`commit 5ae148b`) — `screens/intake/IntakeScreen.tsx`. Largest screen. Paste
  panel (kind toggle, author input, textarea, live SUGGESTED-MARKET hint driven by
  `pmData.suggestMarket`), loaded queue with status dot, kind icon, click-to-edit retag
  dropdown, and confirm/reject/remove actions, warn-line footer, and the
  `RebuildModal` diff preview that groups confirmed entries by market and renders proposed
  appends to `recent_catalysts.md` as a +/= diff. All mutations are local state only —
  nothing is written. `showRebuild` is owned inside the screen, not lifted to App.

### IPC bridge (live)

Implemented end-to-end in `gui/src/main/ipc/` and exposed on `window.pm` via
`gui/src/preload/index.ts`. Shared types live in `gui/src/shared/contract.ts`.

- `readContext()` parses `market_registry.yaml`, `live_state.yaml`, `portfolio_current.yaml`,
  `open_orders.yaml`; stats those files for freshness; lists `data/snapshots/*.json`. Returns
  a `PmDataPayload` (data only — formatting/lookup helpers stay in the renderer). Markets
  carry registry fields only; per-snapshot mark/bid/ask/spread/liq/hist read 0/`[]` until
  snapshots exist. `catalysts: []` per market — `recent_catalysts.md` is section-based not
  market-keyed, so the per-market timeline is empty until a structured catalysts file lands.
- `runStage(name, args)` / `runStageStream(name, args, onChunk)` spawn
  `<.venv/bin/python|python3> -m polyberg.cli <name>` with the 9-stage CLI allowlist
  enforced in `runStage.ts`. Stream variant pipes stdout/stderr chunks through ipcMain →
  renderer keyed by request id.
- `appendCatalyst(marketId, {t, src, txt})` validates marketId against the registry and
  inserts a bullet under `## Credible Reporting Watch` in `recent_catalysts.md`.
- `writeDraftOrder(order)` validates `marketId/side/kind`, `price ∈ (0,1)`, `shares > 0`;
  parse-and-dump appends to `buy_orders` or `sell_orders` in `open_orders.yaml`. The file
  was reformatted on the first write — comments would be lost (the file currently has none).
- `onContextChange(cb)` watches `context/`, `reports/generated/`, `data/snapshots/` via
  chokidar (pinned to v3 — v5 is ESM-only and the main bundle is CJS). 300 ms debounce,
  per-window subscription, cleaned up on `webContents.destroyed`.

Read paths gated to those three directory roots; write paths gated to
`context/recent_catalysts.md` and `context/open_orders.yaml`.

### Renderer (live data)

`<PmDataProvider>` in `gui/src/renderer/src/lib/pmDataContext.tsx` wraps `<App />` in
`main.tsx`. It calls `window.pm.readContext()` on mount, attaches helpers
(`fmtUsd/fmtPct/fmtCents/suggestMarket/marketById`), and re-fetches whenever
`window.pm.onContextChange` fires. `usePmData()` returns the typed `PmData`;
`usePmDataRefresh()` returns the manual refresh fn.

`gui/src/renderer/src/lib/pmData.ts` shrunk to two factory exports
(`makeSuggestMarket`, `makeMarketById`); the bundled fixture is gone. All eleven consumer
files migrated from module-level `pmData` import to `const pmData = usePmData()` inside
each component. `Treemap` takes `marketById` as a prop. Empty-state guards added in
`SnapshotsScreen`, `CatalystsScreen`, `MarketsScreen`, `PositionCard`, `Strips`.

Polish from the visual-first pass: dashboard layout made robust at narrow widths (the
right rail used to clip when snap-tiled to half-screen because Electron's minWidth was
forcing the renderer past the visible area), the intake retag `<select>` text was
switched from white to cyan to match its magenta border, and a new `C.cyanText` token
(`#5cf3d3`) was introduced for body-text accents in catalysts and markets — per-row
EDIT picks up the tint while `+ NEW CATALYST` / `+ ADD MARKET` stay white to mark the
panel-level "create" action distinctly.

### Action surfaces wired

- **RUN NEXT STAGE** (TopBar + WorkflowRail) → finds the first non-`ok` workflow stage
  whose CLI is in the bridge allowlist, opens `<StageRunnerModal>` that streams
  `runStageStream` stdout/stderr into a scrollable monospace pre and shows exit-code
  status. Pre-existing pending-intake diversion preserved (jumps to intake screen if
  there are unreviewed items).
- **Draft order WRITE** (PositionCard → expand → DRAFT ORDER tab) → form is fully
  editable (side toggle, kind toggle, price/shares text inputs, optional notes, live
  YAML preview, computed notional). WRITE calls `window.pm.writeDraftOrder(...)`; the
  watcher refresh propagates the new entry into the OPEN ORDERS pane on the next tick.
  Validation matches the main-process invariants.
- **+ NEW CATALYST** (Catalysts tab) and **+ ADD CATALYST** (PositionCard → CATALYSTS
  pane) → toggle a `<CatalystForm>` (timestamp prefilled to now, source, body); APPEND
  calls `window.pm.appendCatalyst(...)` and the watcher pushes the update.
- **$ REFRESH** (TopBar) → forces an immediate `readContext()` (also still triggered by
  the file watcher).
- **$ import-account-snapshot** (RightRail) → opens the stage runner modal. Requires
  `POLYMARKET_US_API_KEY_ID` and `POLYMARKET_US_SECRET_KEY` env vars; without them the
  modal shows the error.

`+ CONNECT GROK` and the entire "sentiment · grok" box were removed in this session,
along with the `Sentiment` / `SentimentEntry` / `Lean` types and the `sentiment` field
on `PmDataPayload`.

Note (corrected 2026-05-10 after initial removal): the Grok API *does* expose a live
X search/firehose tool, contrary to what was claimed when the stub was first stripped.
The constraint is a per-query cap of ten "allowed" accounts, so practical use needs
either a static configured list of high-signal handles or a rotation of multiple
calls whose results are aggregated. A future revival would design around that cap —
likely a small set of curated handles per market category (oil-desk handles for the
Brent market, maritime-intelligence handles for Hormuz, etc.) plus a BYOK key flow
through xAI direct or OpenRouter.

### localStorage persistence

`gui/src/renderer/src/lib/useLocalState.ts` wraps `useState` with a localStorage
hydrate-on-init / persist-on-change pattern, both wrapped in try/catch so a quota or
serialization failure degrades silently to in-memory state.

- `polyberg:dashboard.expanded` — last expanded position id on the Dashboard tab.
- `polyberg:intake.queue` — the IntakeScreen queue items (paste-panel additions survive
  a window reload). Real source for intake is still the GUI itself; the read-only
  context files don't carry intake data.

### Packaging

`gui/electron-builder.yml` produces an AppImage and a `.deb` from `gui/dist/` via
`npm run dist:linux`:

- `appId: com.polyberg.terminal`, `productName: Polyberg Terminal`, asar with chokidar
  unpacked, deb runtime deps include `libsecret-1-0` so the keyring is available.
- Icon at `gui/build/icon.png` (512×512, rendered from `gui/build/icon.svg`).
- `gui/build/` is force-tracked despite the top-level `build/` gitignore line, via a
  negation rule (`!gui/build/`, `!gui/build/**`).
- A first build downloads `electron-v32.3.3-linux-x64.zip` (~107 MB) and the AppImage
  builder; subsequent builds cache those.

The packaged binary needs `POLYBERG_REPO=<repo path>` set, since `findRepoRoot()` first
honors that env var, then walks up from `__dirname` (which won't reach a repo when the
binary lives under `/opt/Polyberg Terminal/` from a deb install). Missing → clear error
on launch.

### Next phase — account import workflow (priority #1 next session)

This is the headline deliverable for next session. The current `import-account-snapshot`
CLI lands raw authenticated Polymarket US JSON under `reports/generated/account/` but
there's no GUI flow to view that output, promote it into canonical context, or use it
as a ground-truth source for resolution rules. Three paths, all strictly read-only:

1. **Live authenticated account view (read-only).** Surface raw account-import results
   in a new `ACCOUNT` tab (or panel within Dashboard's RightRail). Display:
   imported positions / balances / open orders side-by-side with the canonical
   `portfolio_current.yaml` / `open_orders.yaml` so diffs are obvious. Add an explicit
   "PROMOTE TO CONTEXT" affordance that requires user confirmation per file. No
   automation — manual review is the point. Already-allowlisted: the
   `import-account-snapshot` CLI runs from RightRail's button.
2. **Resolution-rule sync against Polymarket's official rules.** Authenticated account
   import (or a sibling read-only endpoint) returns the official rule text per market
   alongside positions/balances. Pull that field, store it under
   `reports/generated/account/rules/<market_id>.md` (or similar), and surface a
   diff-against-registry view in the GUI: left pane is the registry's manually-entered
   `notes` / `rule_risk` for each market, right pane is the official Polymarket text.
   Highlight divergence so the user can spot when a manual rule entry has drifted from
   the canonical source. PROMOTE-TO-REGISTRY writes the official text into the
   registry's `notes` field after explicit confirmation. Critical for catching
   wording-risk markets where manual paraphrase has lost a "consecutive hours"
   qualifier or similar — the kind of detail that turns a clean YES into a disputed
   resolution. Same auth path as #1, so the implementation cost is mostly UI.
3. **Manual entry via screenshot-to-LLM.** For users who don't want the authenticated
   import path, the GUI provides:
   - A copy-to-clipboard prompt block tailored to portfolio + open-order extraction,
     formatted for paste into Claude or ChatGPT alongside a screenshot of the
     Polymarket portfolio/orders UI.
   - The prompt forces a strict JSON output that matches the same shape as
     `portfolio_current.yaml` / `open_orders.yaml` (probably referencing the existing
     Pydantic schemas via `schemas/`).
   - A paste-back textarea in the GUI that validates the JSON against the schemas and
     previews a write-diff before any file is touched.
   - Confirm → write to context. No automation, no execution, audit trail in the diff.

Both paths preserve the project's hard safety boundary: no order placement, no wallet
keys, no automation. The workflow is "human captures state → human reviews diff →
human writes." The screenshot/LLM step is the user's existing process formalized so
the output lands in the right schema on the first try.

### Next phase — per-market high/low ranges (priority #2)

Goal: surface 1d / 1w / 1m (and probably since-position-open / all-time) high and low
prices for each tracked market on the Dashboard Positions tab, so limit-buy and
limit-sell placement is grounded in recent extremes rather than just the current mark.
Display lives in `PositionCard`'s expanded body — either as additional cells in the
existing `Mini` strip (next to BID / ASK / SPREAD / LIQ / SNAP) or as a small
dedicated row above the price chart.

The feature is mostly a Python-side data-source decision; the GUI render is small once
the data exists. Pick the source first:

1. **Snapshot accumulation.** Schedule `snapshot-markets` at a cron-like cadence so
   `data/snapshots/*.json` builds up a price-series. Compute highs/lows by scanning
   the snapshot files in `readContext()`. Honest but blocked: the current
   `snapshot-markets` CLI emits placeholder snapshots only — `snapshots.py` doesn't
   yet capture real prices. Would need to flesh that out first, then accumulate for
   at least a window before the feature returns useful data. Slow ramp.
2. **Direct historical pull from Polymarket Gamma.** The Gamma collector module is
   currently `NotImplementedError`. Implement a read-only price-history fetch keyed by
   market id, return a `[{ts, mark}]` series, compute highs/lows per window in the
   bridge's `readContext()`. Fast: returns useful data immediately, no accumulation
   wait. Keeps the no-execution boundary (read-only HTTPS, same posture as
   `import-account-snapshot`).
3. **Hybrid.** Cache historical pulls into `data/snapshots/` so subsequent reads are
   local; refresh on demand. Best long-term, more upfront wiring.

Option 2 is probably the right starting point given the empty snapshots directory and
no need to wait days for accumulation. Tasks if we go that route:

- Flesh out `src/polyberg/gamma_collector.py` (or wherever the placeholder lives) with
  a `fetch_price_history(market_id, lookback)` helper using the public Gamma endpoint.
- New CLI subcommand `fetch-price-history` (added to the bridge allowlist) so the GUI
  can request a refresh on demand without crossing the safety boundary.
- Extend `Market` in `shared/contract.ts` with `highs: {d1, w1, m1}` and `lows: {…}`.
- Extend `readContext()` to read the cached series and compute the windows.
- Render in `PositionCard` expanded body. Tint highs cyan, lows red to match the
  existing Spark/PriceChart conventions.

### Next phase — Grok revival (priority #3, framing TBD)

After the API correction (see Grok note above), reviving sentiment is back on the
table for next session. The framing decision is deferred — pick during build —
between two designs:

- **Scan-and-promote to catalysts** *(my recommendation)*: per-market "scan now"
  button anchors a Grok live-X query on a curated handle list (e.g. `@USNI
  @LloydsList @maritimebrief` for Hormuz; `@IEA @EIAgov @OPECSecretariat` for
  Brent), returns a few bulleted observations with raw tweet URLs for spot-checking,
  and offers a per-bullet PROMOTE-TO-CATALYSTS write to `recent_catalysts.md` after
  explicit user OK. Matches the existing manually-curated catalysts workflow.
  Output is reviewable bullets, not numeric scores. No always-on widget. Stays out
  of the packet pipeline so model trust surface doesn't widen.
- **Always-on sentiment panel**: WorkflowRail widget showing score / lean / asOf
  per market, refreshable on demand. Risks: refresh-mashing cost, decoration
  without action, hallucinated paraphrase that's hard to audit, possible drift
  toward feeding sentiment into packets which compromises the safety posture.

Common scaffolding either way:

- BYOK key flow: `safeStorage` (libsecret on Linux, keychain on macOS, DPAPI on
  Windows) gated behind a settings modal. Internal `getApiKey('xai')` helper in
  main, never exposed to renderer.
- Direct xAI API (`api.x.ai/v1/chat/completions`) preferred over OpenRouter for
  the live-search tool — confirm OpenRouter passes those tool params through
  before committing.
- Per-query handle list lives next to the registry, probably in
  `context/market_registry.yaml` as a new optional `sentiment_handles: [...]`
  field (≤10 entries enforced).
- Cost guardrails: per-day spend cap configurable; per-call confirm above some
  threshold.
- Hallucination mitigation: require Grok to return raw tweet URLs alongside its
  bullets. Validate the returned JSON against the existing
  `schemas/twitter_sentiment_response.schema.json` (which exists for exactly this
  contract).

### Medium-term — History tab

After the next-session priorities and before any of the post-v1.0 roadmap items, add a
seventh top-level tab: `HISTORY`. Becomes useful only once the account-import flow has
been running for a while (so there's a stream of snapshots to diff against), so it's
explicitly downstream of the priority-#1 work.

Sources of truth, in roughly increasing fidelity:

- **Closed positions from accumulated account snapshots.** Diffing successive
  `reports/generated/account/` imports surfaces positions that disappeared (closed)
  with the entry side / avg / shares from the earlier snapshot and the inferred exit
  price from the later one. Realized P&L per market falls out of that diff.
- **Trade tickets in `reports/generated/`.** Each `build-trade-ticket` run emits a
  markdown ticket. These are the *decisions*, even when execution didn't happen —
  having them on the History tab is the audit trail "I considered doing X on date Y."
- **Postmortems in `reports/postmortems/`.** Already a directory in the repo, no
  files yet. Designed for human-written "what went wrong / what worked" notes after
  a position closes. The History tab links each closed-position row to its
  postmortem (or shows an empty state inviting the user to write one).
- **Adjudicator outputs.** When present, the adjudicator JSON for a closed position
  is the chain-of-decision: which trader prompt, which risk critic, which final
  call. Surface as drill-down detail.

UI shape:

- Timeline-style table on the left: closed-position rows sorted by close date
  (date, market, side, entry/exit, hold time, realized P&L, postmortem present?).
- Right pane: drill-down with the linked packet / adjudicator / trade-ticket /
  postmortem files inlined, each in its own collapsible panel.
- Top of the screen: cumulative metrics (total realized P&L, win rate, average
  holding period, P&L by category, biggest win, biggest loss).
- Filters: by market, date range, realized return sign, category, postmortem
  presence.

Implementation order:

1. Bridge: `readClosedPositions()` returns `ClosedPosition[]` derived from snapshot
   diffs. Lives in `gui/src/main/ipc/history.ts`. Reads-only — no writes.
2. New IPC method `readPostmortem(marketId, ts)` and writer
   `writePostmortem(marketId, ts, body)` for the inline editor (gated to
   `reports/postmortems/` only).
3. Renderer: new `screens/history/HistoryScreen.tsx` plus a tab in `App.tsx`.
4. Cumulative metrics computed in the bridge, not the renderer (so they stay
   correct under file watcher refreshes).

Non-goals for this tab: live position monitoring (that's the Dashboard), forward-
looking suggestions (that's the packet flow). HISTORY is strictly retrospective.

### Long-term roadmap (post-v1.0)

These are explicitly *not* next-session items. Drop here so they don't get lost.

- **Windows port**: code is mostly platform-agnostic already. Real fixes needed:
  `runStage.ts` picks `.venv/bin/python` — needs `.venv/Scripts/python.exe` on
  Windows; chrome-sandbox setuid is Linux-only and irrelevant on Windows; add
  `nsis` / `portable` / `msi` targets to `electron-builder.yml`. Estimate: half
  a day if the polyberg repo runs on Windows already (Python's `pathlib`, the
  Pydantic models, and `cli.py` are Windows-safe per the existing
  `Windows-safe path and timestamp conventions` note).
- **Multiple themes**: current palette is hardcoded in
  `gui/src/renderer/src/styles/tokens.ts` as `colors as C` and `fonts as F`.
  Theming work: factor the palette out into a `<ThemeProvider>` keyed off a
  user setting (localStorage), expose `useTheme()` returning the current
  palette, and replace the ~50 `C.*` references across screens with the hook.
  Tokens themselves stay; the swap is at the resolution boundary. Probably one
  day of work plus designing a second / third palette. Candidates: amber-on-
  black (Bloomberg), green-on-black (CRT classic), high-contrast light.
- **Android app**: more ambitious than it sounds because Electron is desktop-
  only. Options:
    - **Capacitor**: wraps the existing React renderer in a webview,
      smallest delta, but the IPC bridge would need a complete rebuild — no
      shell-out to Python is possible on stock Android. Would require running
      polyberg as a server (local Termux + Python, or remote) and changing
      `window.pm` to talk HTTPS to that server. Significant.
    - **React Native**: full rewrite of the renderer in native components.
      Same IPC re-architecture. Months of work.
    - **Tauri Mobile**: lighter but less mature, similar IPC re-architecture.
  All three break the local-first assumption (no Python on the device) so the
  Android app is really a *thin client over a server polyberg*. That server
  layer is its own scope and probably the actual blocker. Worth designing the
  server contract first, before picking the mobile framework.

### Other deferred work

- Cosmetic stubs still no-op: search bar (⌘K), filter buttons.
- `recent_catalysts.md` could be restructured to per-market sections so the catalyst
  timeline on each tab has data; today the file is section-based and the GUI shows
  empty timelines.
- Workflow-stage detection in `readContext.ts` probes guessed filenames in
  `reports/generated/` (`packet.md`, `model_a_validation.txt`, etc.) — tighten once
  the report layout stabilizes.

### Frame note

The prototype's `transform: scale()` Frame was dropped — Electron sizes the window directly.
At widths below ~1300 the dashboard's `gridTemplateColumns: '540px 1fr'` expanded body gets
cramped. Min window size is 1200×800 in `main/index.ts`; bump or make responsive when needed.

## Current Shape

- Package: `polyberg`
- Runtime: Python 3.11+; local virtualenv currently runs Python 3.12.3.
- Primary target: Ubuntu/Linux, with Windows-safe path and timestamp conventions.
- Package layout: `src/` package, `tests/` pytest suite, repo-local `context/`, `schemas/`,
  `prompts/`, generated output folders, and docs.
- Dependencies: `pydantic`, `pyyaml`, `jsonschema`, `rfc3339-validator`, `cryptography`, and
  Windows-only `tzdata`.
- Developer tooling: `pytest`, `ruff`, `Makefile` wrappers.

## Main Workflow

1. Update local context files in `context/`.
2. Optionally create a placeholder/read-only market snapshot.
3. Build a research packet with `build-packet`.
4. Paste the packet into model prompts and save model JSON outputs.
5. Validate model JSON with `validate-response`.
6. Build adjudicator input from packet plus two model outputs.
7. Paste adjudicator input into an adjudicator model and save adjudicator JSON.
8. Validate adjudicator JSON with `validate-adjudicator`.
9. Build a human trade ticket with `build-trade-ticket`.
10. A human manually reviews any recommendation before acting on Polymarket.

## Command Surface

The CLI is implemented in `src/polyberg/cli.py` and exposes these subcommands:

- `build-packet`
- `validate-response`
- `validate-adjudicator`
- `build-adjudicator-input`
- `snapshot-markets`
- `diff-snapshots`
- `build-trade-ticket`
- `import-public-positions`
- `import-account-snapshot`

The command surface deliberately avoids execution verbs such as place, create, cancel, modify,
execute, wallet, and private-key.

## Core Modules

- `models.py`: strict Pydantic models for market registry entries, live state, portfolio, open
  orders, rule risk, and market snapshots. Extra fields are forbidden. Market IDs must be lowercase
  letters, numbers, and underscores. Timestamps must include timezone offsets.
- `loaders.py`: reads YAML/text context files, parses Pydantic models, and verifies portfolio,
  open-order, and watchlist market IDs exist in the registry.
- `packet_builder.py`: builds the main markdown research packet. It includes model instructions,
  missing-info warnings, freshness audit, live state, portfolio, exposure summary, open orders,
  market registry, optional snapshot summary, catalysts, trading principles, and stable rules.
- `validators.py`: validates JSON files against local JSON schemas and then runs business checks
  such as timezone-aware `as_of`, known market IDs, and market-name consistency.
- `adjudicator_builder.py`: combines adjudicator instructions, the research packet, and two model
  outputs into a markdown adjudication packet.
- `trade_ticket.py`: validates adjudicator output, then renders a markdown trade ticket that
  emphasizes human review and that no orders were placed.
- `snapshots.py`: creates placeholder market snapshots from the registry and diffs old/new
  snapshots for price, spread, liquidity warning, and missing-info changes.
- `config.py`: centralizes repo-relative paths, timezone handling, freshness threshold, and
  Windows-safe timestamps.

## Context Files

- `context/market_registry.yaml`: stable list of tracked markets, IDs, URLs, categories, rule keys,
  oracle types, preferred sides, resolution dates, optional Gamma/CLOB identifiers, and rule-risk
  metadata.
- `context/live_state.yaml`: current operating mode, account snapshot, active thesis, constraints,
  watchlist, and notes.
- `context/portfolio_current.yaml`: current portfolio value, cash, and positions.
- `context/open_orders.yaml`: manually tracked buy/sell limit orders.
- `context/recent_catalysts.md`: manually curated catalysts, rumors, and missing context.
- `context/trading_principles.md`: durable trading discipline.
- `context/stable_rules.md`: resolution-rule reference material.

At review time, tests expect 3 markets in the registry and use IDs such as
`hormuz_normal_may15`, `cl_high_120_end_june`, and `trump_blockade_lifted_apr30`.

## Prompts And Schemas

Prompts:

- `prompts/claude_trader_prompt.md`: trade idea generator prompt.
- `prompts/chatgpt_risk_prompt.md`: risk/resolution-rule critic prompt.
- `prompts/adjudicator_prompt.md`: adjudication prompt.

Schemas:

- `schemas/model_trade_response.schema.json`: candidate trade output contract.
- `schemas/adjudicator_output.schema.json`: final adjudicator output contract.
- `schemas/market_snapshot.schema.json`: market snapshot contract.
- `schemas/twitter_sentiment_response.schema.json`: future noisy/catalyst-only social sentiment
  contract.

Important schema/business rules include:

- `human_review_required` must be present and true.
- Prices are bounded from 0 to 1.
- Sides are restricted to `YES` or `NO`.
- Market references must resolve to `context/market_registry.yaml`.
- Model market names must match the registered market name.
- `as_of` must be timezone-aware.
- Orders are limit-only where the local model uses an order type.

## Data Collection And Account Import

The project has partial read-only account import support:

- Public positions by wallet/proxy-wallet address via the public Polymarket Data API.
- Authenticated read-only Polymarket US imports for positions, balances, and open orders.
- Authenticated requests are GET-only and signed with environment-provided
  `POLYMARKET_US_API_KEY_ID` and `POLYMARKET_US_SECRET_KEY`.
- Raw account imports are written to generated JSON files and are not automatically promoted into
  canonical context.

The Gamma and CLOB collector modules are placeholders. Their fetch functions currently raise
`NotImplementedError`; only small normalization helpers are present.

## Safety Boundaries

The project repeatedly enforces these boundaries:

- No automated trading.
- No order placement, cancellation, modification, or execution.
- No wallet private-key integration.
- No browser automation.
- No scraping.
- No dashboard or Streamlit UI.
- Twitter/X sentiment is considered noisy, catalyst-only, and non-authoritative.
- Local freshness checks audit file timestamps only; they do not verify live markets, news, oracle
  data, or order books.

## Test Coverage

The suite currently has 42 passing tests in the local virtualenv.

Covered areas:

- CLI command surface avoids execution-like commands.
- YAML context loading and cross-reference validation.
- Pydantic validation for timestamps, market IDs, order type, and live-state mode.
- Packet sections, snapshot inclusion, alternate context directory support, and heading
  normalization.
- JSON schema validation for model, adjudicator, and snapshot files.
- Business validation for known market IDs and matching market names.
- Human-review-required enforcement.
- Snapshot generation and diffing.
- Read-only HTTP account import behavior, address validation, signed path construction, and
  GET-only restrictions.
- Trade ticket generation and routing of nonstandard actions into "Other Final Orders".

Verification command used:

```bash
.venv/bin/python -m pytest
```

Result:

```text
42 passed
```

## Likely Update Areas

1. Implement real read-only Gamma and CLOB collectors, keeping the no-execution boundary explicit.
2. Add normalization for imported positions, balances, and open orders.
3. Add a reviewed promotion workflow from raw imports into `context/portfolio_current.yaml`,
   `context/open_orders.yaml`, and `context/live_state.yaml`.
4. Improve market snapshot generation so it can include real prices, spreads, top-of-book depth,
   and missing-info diagnostics.
5. Add tests around any real network-client code with fake openers/clients, preserving deterministic
   offline test behavior.
6. Consider a generated run manifest that records packet input file hashes, snapshot path, schema
   versions, and validation results for auditability.
7. Consider a context freshness/update helper that reports exactly which context files need manual
   refresh before packet generation.

## Operational Notes

- `python` is not available on this machine path; use `.venv/bin/python` or `python3`.
- System `python3` does not have pytest installed; the repo virtualenv does.
- The repository checked for this summary is `/home/cleblanc/projects/autoAchaemenes/polyberg`.
- The parent directory `/home/cleblanc/projects/autoAchaemenes` is not itself a git repository; the
  project directory is the meaningful working directory.
