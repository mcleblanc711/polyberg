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

   **Status (v1, shipped):** `AccountScreen` tab renders side-by-side imported-vs-
   canonical for all three files, with empty-state pointing at `$ import-account-snapshot`.
   PROMOTE buttons are present but disabled — the normalizer (raw API JSON → canonical
   schema) cannot be written without a captured real-API response sample to validate
   field names against. Note: the existing `import-account-snapshot` CLI is wired against
   the authenticated Polymarket US endpoint, which requires API keys most users won't
   have — v2 pivoted the default importer to the main Polygon Polymarket endpoints
   (`data-api.polymarket.com` for positions-by-wallet, etc.), which are unauthenticated.

   **Status (v2, shipped):** Pivoted to the unauthenticated Polygon `data-api.polymarket.com/positions`
   endpoint, which is wallet-keyed and doesn't require keys. `live_state.yaml` now carries
   `proxy_wallet`. The GUI's import button fires `import-public-positions --address <wallet>`
   and writes `reports/generated/account/positions_data_api.json`. A new
   `src/polyberg/account_normalizer.py` maps that response onto the canonical `Portfolio`
   schema by `conditionId` ↔ registry lookup; `thesis_bucket` annotations on existing positions
   survive promotion. New CLI `promote-positions` supports `--dry-run` (stdout YAML, stderr
   skipped list) and a real write to `context/portfolio_current.yaml`. PROMOTE in the GUI
   previews the dry-run output in a modal before committing. Tests live in
   `tests/test_account_normalizer.py` (5 tests against the sanitized real-API fixture at
   `tests/fixtures/account_import/positions_data_api.json`). Also: bumped `ReadOnlyHttpClient`
   to send a `User-Agent` header so both data-api and CLOB stop 403-ing the Python client.

   **v2 known gap:** balances and open orders aren't normalized — `data-api` doesn't expose
   those without authentication, and the default importer path stays unauthenticated. The
   Balances / Open Orders tabs in `AccountScreen` are present but their PROMOTE is
   permanently disabled with a "needs authenticated path" note. Closing this requires
   either (a) on-chain USDC balance fetch via a public RPC for the proxy wallet, plus
   open orders from the CLOB; or (b) the existing authenticated Polymarket US path for
   users who have those keys.

   **v2 data-population gap (not code):** the example `context/market_registry.yaml`
   ships with empty `condition_id` values for all three demo markets. Until those are
   populated per market, the normalizer correctly skips every imported position with
   "conditionId not in registry" — the registry is the source of truth for which markets
   are in scope, and silently promoting positions for off-registry markets would defeat
   the manual-review point.
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

### Next phase — open-orders cash exposure (priority #2)

Goal: at-a-glance view of "if every open limit buy filled right now, how much cash
would that consume, and how does that compare to the cash on hand in the portfolio?"
Currently the GUI shows positions and orders but never sums commitment vs available
cash, which is the number that actually governs whether new orders can be placed.

Visual: match Polymarket's own `portfolio` / `cash` bar treatment (their split-bar
showing portfolio value vs free cash) but rendered in the Polyberg palette — cyan
for cash on hand, magenta or amber for committed-to-open-buys, red tint when
commitments exceed cash. Numeric labels in the existing terminal font. Probably a
small dedicated strip rather than a full panel.

Placement: in the Dashboard's RightRail, directly below the account-login / account
status block (priority #1's home), high in the visual hierarchy because it's a
go/no-go signal for any new draft order.

Implementation sketch:

- `open_orders.yaml` already has `price` and `shares` per buy entry — sum
  `price * shares` across `buy_orders` for the owing total.
- `portfolio_current.yaml` carries `cash` — the comparison side.
- Both are already loaded in `readContext()`. Computation can live entirely in the
  renderer; no new IPC.
- Add a `<CashCommitmentBar>` component under `screens/dashboard/` rendering the
  split bar plus dollar labels. Reuse `fmtUsd` from the format helpers.
- Edge cases: no open buys (bar fully cyan), commitment > cash (amber/red tint
  with explicit overage label), no portfolio loaded (empty state).

### Next phase — market telemetry layer (priority #3)

Captured from a ChatGPT brief (2026-05-14) that supersedes the earlier "per-market
high/low ranges and price history" framing. Goal: record Polymarket price history for
every tracked market and derive a compact, **deterministic, rule-based** feature set
that helps trade review answer four questions: has the market already repriced, was
the move gradual or sudden, is this likely emotional liquidity, and should ladders
tighten / widen / stay passive. This is **market telemetry for decision context, not
technical analysis** — no LLM inference of labels, no signal/strategy framing.

**Path translation** (the brief uses old-style `scripts/` + `live/` paths; polyberg
has matured along a different layout):

| Brief path / artifact | Polyberg equivalent |
|---|---|
| `scripts/snapshot_prices.py` | new module `src/polyberg/price_snapshots.py` + CLI `polyberg snapshot-prices` |
| `scripts/price_features.py` | new module `src/polyberg/price_features.py` + CLI `polyberg price-features` |
| `scripts/render_market_telemetry.py` | new module `src/polyberg/market_telemetry.py` + CLI `polyberg render-market-telemetry` |
| `live/prices/raw_price_events.jsonl` | `reports/generated/prices/raw_price_events.jsonl` |
| `live/prices/history/<asset_id>.json` | `reports/generated/prices/history/<asset_id>.json` |
| `live/prices/features.json` | `reports/generated/prices/features.json` |
| `live/prices/market_notes.md` | `reports/generated/prices/market_notes.md` |
| `GET /api/price_history/{asset_id}` | `window.pm.readPriceHistory(assetId)` IPC |
| `GET /api/price_features` | `window.pm.readPriceFeatures()` IPC |
| `GET /api/market_telemetry` | `window.pm.readMarketTelemetry()` IPC |
| `session_bootstrap.py` integration | step in `polyberg session-bootstrap` (priority #6) |

**Data source decision is settled by the brief:** use the public CLOB
`POST https://clob.polymarket.com/batch-prices-history` endpoint in chunks of 20
asset_ids, pulling 1h interval for the last 72h and 1d interval for the last 30d.
This deprecates the earlier "Gamma vs snapshot accumulation vs hybrid" choice — CLOB
batch-prices-history is unauthenticated, returns full series in one request, and
keeps the read-only / no-execution posture intact. The earlier idea of fleshing out
`gamma_collector.fetch_price_history` is dropped.

**Deliverables, in order:**

1. **`snapshot-prices` CLI + module.**
   - Read tracked asset_ids from the union of `context/market_registry.yaml`,
     `context/portfolio_current.yaml`, and `context/open_orders.yaml`. Deduplicate.
   - POST to `clob.polymarket.com/batch-prices-history` in chunks of 20.
   - Pull 1h interval for the last 72h **and** 1d interval for the last 30d
     (two passes per chunk; keep both granularities downstream).
   - Append the **raw API response JSON** (one line per chunk request) to
     `reports/generated/prices/raw_price_events.jsonl` with `{as_of, asset_ids,
     interval, lookback, response}`. Raw-first storage is a cross-cutting
     requirement (see priority #8).
   - Write per-asset normalized history to
     `reports/generated/prices/history/<asset_id>.json` with `schema_version`,
     `as_of`, the merged 1h+1d series, and a `raw_ref` pointing back at the raw
     jsonl line. Preserve any extra Polymarket fields under a `raw_ref` block
     rather than dropping them.
   - Expose `run() -> dict` (count fetched, count skipped, error list) so
     `session-bootstrap` can drive it.

2. **`price-features` CLI + module.**
   - Read normalized histories.
   - Emit `reports/generated/prices/features.json` with `schema_version` and a per-
     `asset_id` block containing: `current_price`, `price_{1h,6h,24h,72h,7d}_ago`,
     `change_{1h,6h,24h,72h,7d}`, `daily_changes_last_3`, `daily_changes_last_7`,
     `high_7d`, `low_7d`, `distance_from_7d_high`, `distance_from_7d_low`,
     `realized_vol_72h`, `max_drawdown_72h`, plus three **deterministic, rule-based**
     labels: `trend_label` (e.g. `steady_uptrend` / `range_bound` / `adverse_drift`),
     `spike_label` (e.g. `headline_spike` / `none`), `execution_implication`
     (e.g. `tighten_ladder` / `widen_ladder` / `stay_passive` / `consider_fade`).
   - Labels are **not LLM-generated.** The thresholds live in code so behavior is
     reproducible across runs and reviewable in a diff.

3. **`render-market-telemetry` CLI + module.**
   - Write `reports/generated/prices/market_notes.md`, grouped by `cluster_key`
     (sourced from `market_registry.yaml`). Each cluster block lists per-asset
     compact summaries — small enough to embed inside an LLM prompt packet without
     blowing the context budget. Avoid pretty charts; this is text the model reads.

4. **`session-bootstrap` integration** (extends priority #6).
   - Insert `snapshot-prices.run()` → `price-features.run()` →
     `render-market-telemetry.run()` between cross-venue-check and the state diff.
   - Wrap each step so a CLOB outage doesn't kill the bootstrap chain (same
     pattern as the Portwatch collector).

5. **Electron IPC** (no FastAPI — see "API surface" decision in this session):
   - `window.pm.readPriceHistory(assetId)` → returns the normalized history file.
   - `window.pm.readPriceFeatures()` → returns the full `features.json` payload.
   - `window.pm.readMarketTelemetry()` → returns the rendered markdown notes.
   - All three read-only; gated to `reports/generated/prices/` like the other
     bridge readers.
   - **`window.pm.readReviewPacket()`** also includes the price-features block in
     its payload (see priority #8).

6. **GUI surface.** With features wired to IPC, surface them in two places:
   - `PositionCard` expanded body: a small telemetry strip (1h / 24h / 7d change,
     distance-from-7d-high/low, current `execution_implication` chip). Tint moves
     amber/cyan/red per existing palette conventions.
   - A dedicated `MARKET TELEMETRY` panel inside the existing `MARKETS` tab (or a
     new sub-tab) showing the rendered `market_notes.md`, grouped by cluster, for
     fast scan before a session.

7. **Tests.** `tests/test_price_features.py` against four synthetic series:
   `steady_uptrend`, `headline_spike`, `range_bound`, `adverse_drift`. Assert both
   the numeric `change_*` values and the categorical labels match expected output.
   Deterministic-label-rules being tested matters more than the absolute thresholds —
   refactoring thresholds is allowed; silently flipping labels is a regression.

**Hard non-goals** (preserved from the brief):

- No order execution. No live websocket. Snapshot on demand only.
- No "technical analysis" framing in the GUI or the markdown output. The labels
  exist to inform decision context, not to generate trade signals. If we catch
  ourselves writing a "BUY" / "SELL" recommendation off the label, that's a bug.

**Relationship to other priorities:**
- **#2 cash-exposure bar** — the ladder cash model in priority #8 consumes
  `current_price` from `features.json` to bucket open buys by distance-from-mark.
- **#6 session-bootstrap** — telemetry steps are inserted as a sub-chain.
- **#7 anti-leak guardrails** — the `CHURN` flag combined with a `headline_spike`
  label can sharpen the kill-switch logic ("position is down 30% AND market just
  spiked AND no sell ladder" is a stronger signal than the position drop alone).

### Next phase — Grok revival (priority #4, framing TBD)

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

### Next phase — Perplexity sensor + domain routing (priority #5)

Captured from a Claude-web brief (2026-05-11) that still names things by the
project's old layout (`scripts/`, `live/`, `ask_both.py`, `CLAUDE.md`,
`AGENTS.md`); polyberg has matured along a different path. **The intent
translates; the paths in the brief do not.** Re-map onto:

| Brief path / artifact | Polyberg equivalent |
|---|---|
| `scripts/perplexity_query.py` | `polyberg perplexity-query` CLI subcommand in `cli.py` |
| `scripts/news_pull.py` | `polyberg news-pull` CLI subcommand |
| `scripts/ask_panel.py` | `polyberg ask-panel` CLI subcommand |
| `scripts/news_themes.yaml` | `context/news_themes.yaml` |
| `live/_perplexity_cache/` | `reports/generated/perplexity_cache/` |
| `live/catalysts.md` | `context/recent_catalysts.md` |
| `CLAUDE.md` / `AGENTS.md` | append to `docs/project_summary.md` |
| `context/05_rules_for_llm.md` | doesn't exist; the system prompt should be assembled from `context/live_state.yaml`'s `active_thesis` + `constraints` + `notes`, the same shape `build-packet` already consumes |

**What it builds** (deliverables, in priority order):

1. **`perplexity-query` subcommand.** OpenAI-compatible client against
   `api.perplexity.ai`. Flags: `--model {sonar, sonar-pro, sonar-reasoning}`
   (default `sonar`; don't expose `sonar-deep-research`), `--recency
   {hour, day, week, month}`, `--domains` (comma-separated allowlist),
   `--max-tokens` (default 1000). Output: model text plus a `Sources:` block
   from response citations — never strip those, they're the point. Cache
   the full response JSON under `reports/generated/perplexity_cache/`.
2. **`news-pull` subcommand.** Loads themes from
   `context/news_themes.yaml` (hormuz / diplomacy / enrichment / military /
   oil_data, each with `query` + `domains`), hits Perplexity per theme with
   a recency filter, and **appends** to `context/recent_catalysts.md` (never
   rewrites — append-only timestamped log). `--theme <name>` runs a single
   theme; default runs all. `--dry-run` prints without appending.
3. **`ask-panel` subcommand.** Replaces the spec's `ask_both.py` /
   `ask_panel.py` distinction (neither exists in polyberg). Modes:
   - `rules` — Claude only (resolution-rule parsing)
   - `adversarial` — Claude + ChatGPT in parallel, displayed side-by-side
   - `news` — Perplexity only
   - `full` — all three, sparingly
   Each model gets the same system prompt assembled from `live_state.yaml`
   plus the user's question. **No synthesis** — print blocks separately;
   independent sensors are the whole point.
4. **Domain-routing reference** in `docs/project_summary.md` (the
   stable docs surface, since polyberg has no `CLAUDE.md` / `AGENTS.md`):
   short table mapping question-type → which subcommand. Default to
   `ask-panel --mode rules` (Claude only) when category is unclear.
5. **`.env` keys.** `PERPLEXITY_API_KEY`, `OPENAI_API_KEY`,
   `ANTHROPIC_API_KEY` documented in a new `.env.example`. Each subcommand
   surfaces a clean error naming the missing key if its sensor isn't
   reachable.
6. **Dependencies.** Perplexity is OpenAI-compatible — reuse the existing
   `openai` package; no new dependency unless the `news_themes.yaml`
   loader needs `pyyaml` (already present per `loaders.py`).

**Out of scope for this priority** (explicit non-goals from the brief, valid
for polyberg too): no GUI surface, no daemon, no synthesis mode, no
`sonar-deep-research`, no refactor of any existing CLI subcommand.

**Relationship to Grok revival (priority #4):** these are sibling sensors,
not duplicates. Perplexity covers the general web with citations; Grok covers
live X with handle-curated queries. Build #4 and #5 as sibling subcommands
(`scan-grok`, `news-pull`) writing to the same `recent_catalysts.md` log so
they compose. Order: do #5 first — Perplexity is unauth-key-but-paid,
clearly documented, OpenAI-compatible; the lift is half of #4's.

### Next phase — session bootstrap pipeline (priority #6, paired with #1 cash gap and #5)

Captured from a ChatGPT brief (2026-05-13) that names things by the project's old
layout (`scripts/`, `live/`, `state/`, `CLAUDE.md`, `AGENTS.md`, `ask_both.py`,
`cross_venue_check.py`); polyberg has matured along a different path. **The intent
translates; the paths in the brief do not.** Re-map onto:

| Brief path / artifact | Polyberg equivalent |
|---|---|
| `scripts/snapshot_portfolio.py` | **shipped** — `polyberg import-public-positions` + `account_normalizer.py` + `promote-positions` (positions side) |
| `scripts/snapshot_orders.py` | **shipped** — CLOB open-orders import landed in P1 v2; rotate creds at session start per [[rotate-clob-creds]] |
| `scripts/state.py` (diff prev/curr) | new — `src/polyberg/state_diff.py`; prev snapshots under `reports/generated/state/` |
| `scripts/render_live.py` (md tables) | mostly **n/a** — the GUI is the render layer; only the stdout summary is worth porting |
| `scripts/session_bootstrap.py` | new CLI `polyberg session-bootstrap` (alias `morning-briefing`) |
| `cross_venue_check.py` | new CLI `polyberg cross-venue-check` (Kalshi Hormuz vs Polymarket) |
| Portwatch IMF feed | new collector `src/polyberg/portwatch_collector.py` (Strait of Hormuz daily transit count, 7-day MA) |
| `live/.cache/markets/` | `reports/generated/.cache/markets/` (Gamma response cache keyed by `condition_id`) |
| `live/`, `state/` directories | `reports/generated/`; canonical state stays in `context/` |
| `CLAUDE.md` / `AGENTS.md` | `docs/project_summary.md` |

**Deliverables, in order:**

1. **Close the cash gap first** — **shipped 2026-05-14.** Resolved empirically:
   both USDC.e (`0x2791Bca1...`) and native USDC (`0x3c499c54...`) return zero
   at the proxy. The proxy is an EIP-1167 minimal-proxy smart contract that
   structurally never holds cash — Polymarket's collateral pool does. New
   collector `polymarket_clob_balance.py` reads `/balance-allowance` via L2
   HMAC auth with `signature_type=1` (POLY_PROXY). New CLI subcommand
   `import-clob-balance` writes `reports/generated/account/usdc_balance.json`
   (same `balance_usdc` field name so the normalizer reads it transparently).
   `polygon_rpc.py` deleted — no correct use case. GUI prefers
   `portfolio_current.yaml.cash_available` over `live_state.yaml`. See
   [[polymarket-cash-source]] for the full empirical write-up.

2. **State-diff module (`src/polyberg/state_diff.py`).** Pure helpers, no CLI of
   its own:
   - `load_current()` reads current positions + orders JSON under `reports/generated/account/`.
   - `load_previous()` reads `reports/generated/state/portfolio.prev.json` and `orders.prev.json`.
   - `diff_positions(curr, prev)` → list of `{market_id, outcome, share_delta, avg_price_delta, action: "opened"|"closed"|"increased"|"decreased"}`.
   - `diff_orders(curr, prev)` — same shape for buy/sell ladders. **Order-close attribution discipline (from the 2026-05-14 brief):** never infer that a disappeared order was filled purely from disappearance. Each closed order carries `closed_reason ∈ {filled, canceled, expired, unknown}` — `filled` requires corroboration from a fills/activity stream; `canceled` and `expired` require explicit signal; otherwise `unknown`. The `unknown` count surfaces in the bootstrap summary and in the review packet so it isn't silently swept under "filled" P&L.
   - `promote(curr)` rotates current → prev. Called at the end of every successful bootstrap so tomorrow's diff is correct.

3. **Cross-venue collector (`polyberg cross-venue-check`).** Kalshi Hormuz markets
   vs Polymarket equivalents. Emit `reports/generated/cross_venue.json` with
   per-market mid/bid/ask on both venues and a divergence column. Supports
   `--discover-kalshi hormuz` on first run of the day to refresh the Kalshi
   market list.

4. **Portwatch collector (`src/polyberg/portwatch_collector.py`).** Pull Strait of
   Hormuz daily transit count CSV from IMF Portwatch (`portwatch.imf.org/...`),
   compute current 7-day MA, emit `reports/generated/portwatch.json`. Wrap network
   failures — Portwatch goes down regularly and must not kill the bootstrap chain.

5. **`session-bootstrap` CLI.** One command for the start of every trading session:
   1. `import-public-positions` (shipped)
   2. CLOB open-orders refresh (shipped)
   3. `cross-venue-check` (new, #3 above)
   4. `portwatch-pull` (new, #4 above)
   5. State diff vs yesterday (new, #2 above)
   6. One-screen stdout summary: equity, cash, top 5 positions by value,
      position deltas vs yesterday, orders filled since last run, current
      Portwatch 7-day MA, cross-venue divergences > 3¢.

   Each step is wrapped — a single source failing (Portwatch outage, Kalshi
   rate-limit) logs and continues. GUI integration: new `$ session-bootstrap`
   button in RightRail that streams stdout through the existing
   `runStageStream` modal.

**Hard requirements preserved from the brief** (already consistent with polyberg's posture):
- Read-only everywhere. No execution endpoints.
- All scripts importable as modules; CLI behind `if __name__ == "__main__"`.
- No SQLite, no MCP, no async unless rate limits force it.
- Test each step against the live wallet before chaining.

**Out of scope here** (per brief, valid for polyberg): no Perplexity wiring
inside bootstrap yet — priority #5 is its home; bootstrap calls it once
`news-pull` lands. No concentration roll-up / sleeve bucketing (waits on
registry maturity). No headline reaction logger.

**Relationship to other priorities:**
- **#1 cash gap** — resolved 2026-05-14. Bootstrap's summary can now lead with real cash via `import-clob-balance` → `promote-positions`.
- **#5 Perplexity** composes naturally with bootstrap; insert as step 4.5 once `news-pull` ships.
- **#2 cash-exposure bar** in the GUI consumes the same numbers bootstrap prints to stdout — build data once, render twice.
- **#7 anti-leak guardrails** consume the state-diff output (the `CHURN` flag needs round-trip counts from accumulated state-diff history).

### Next phase — anti-leak trading guardrails (priority #7, paired with #5)

Same Claude-web brief carries trade-discipline rules grounded in real May 11
attribution data (WTI/oil tail markets: -$102 net across 33 closed positions,
24% win rate; "Other" bucket: 35 markets, net negative; one Hormuz May
contract: 45 round-trip trades for $65 net — thesis carried, churn ate
spread). These are leak patterns, not preferences. Wire them as enforced
validators, not advisory notes.

Concretely:

1. **Scope guardrail.** Block any new draft order whose market is outside
   the US-Iran cluster (Hormuz / peace deal / blockade / enrichment /
   ceasefire / Iran-side political). Implementation: a `cluster` tag (or
   reuse `category`) on each market in `market_registry.yaml`; the draft-
   order write IPC checks the tag and refuses with a clear "off-scope"
   error citing the May 11 attribution.
2. **Oil-tail interdict.** Hard-decline any new draft on a WTI / oil tail
   market unless the user passes an explicit justification override flag
   (or types a confirmation token). Same pattern as #1 but with a
   stronger guard.
3. **Kill-switch flag.** Surface a `KILL-SWITCH` warning in `PositionCard`
   when an open position is >30% below entry AND has no open sell ladder
   for the associated market. Drives the "cut if catalyst passes without
   meaningful repricing" rule from sleeve doctrine.
4. **Churn flag.** Compute round-trip trade count per market (needs the
   accumulated history from priority-#1's account snapshots once
   stacked) and surface a `CHURN` warning above 15 round-trips for any
   active market. Past Hormuz May 45-trade incident is the calibration
   point.

These are deliberately enforced in code, not documented as policy, because
the brief's whole framing is "past sessions have not enforced this fast
enough" — i.e. willpower-based rules don't work; in-code interdicts do.

### Next phase — decision-quality hardening (priority #8, paired with #5 and #6)

Captured from a ChatGPT brief (2026-05-14). The brief frames itself as a three-
session split (data pipeline / workflow intelligence / FastAPI+UI+publication) and
proposes migrating `context/` into `examples/iran-2026/`. **Both framings are
declined for polyberg:** the data-pipeline session is mostly already shipped
(`import-public-positions` + CLOB orders + `account_normalizer`), the
workflow-intelligence session overlaps priorities #5–#7, and the FastAPI+Vite+SPA
session conflicts with the Electron architecture (decision this session: stay on
Electron IPC, no FastAPI). The migration is also declined — `context/` stays as
canonical user-owned state with the never-overwrite-without-approval rule preserved.

What survives is a bundle of cross-cutting **discipline upgrades** to the existing
packet → model → adjudicator → ticket flow. None of these are new pipelines; they
all sharpen surfaces the project already has.

**Deliverables, in roughly increasing scope:**

1. **Schema versioning + raw-payload preservation (cross-cutting requirement).**
   - Every JSON artifact polyberg emits — packets, snapshots, account imports,
     state diffs, price features, disagreement reports, review-packet payloads —
     carries `schema_version: <int>`. Bumped on breaking field changes.
   - Every generated review (model output, adjudicator output, trade ticket)
     carries `source_state_hash`, `as_of`, and `stale_flags[]`. The hash is over
     the concatenated canonical context inputs at generation time, so a reviewer
     can verify the model saw exactly what's claimed.
   - Every collector (account import, CLOB orders, batch-prices-history,
     Portwatch, Kalshi, Perplexity) appends its **raw API response** to a
     `raw_events.jsonl`-style log under `reports/generated/<collector>/raw_*.jsonl`
     before normalization. Normalized records carry either the raw fields inline
     or a `raw_ref: {file, offset}` pointer so the audit trail is recoverable.
   - Where this most needs retrofit today: `account_normalizer.py` (preserve raw
     positions fields under a `raw_ref` block), `snapshots.py` (currently writes
     placeholder snapshots — once real prices land, raw response goes to the
     jsonl log first), and the upcoming price/portwatch/kalshi/perplexity
     collectors (build raw-first from day one).

2. **Review-packet preview (`window.pm.readReviewPacket()`).**
   - New IPC method that renders the **exact packet sent to models** without
     re-running the adjudicator. Mirrors what `build-packet` already produces but
     also bundles: positions, open orders, recent fills/activity, `live_state`
     thesis memory, market registry slice, rules-text refs, current `stale_flags`,
     unresolved reconciliation warnings (e.g. registry has a market that the
     wallet position references but no rules text), the ladder cash model
     (deliverable #4 below), the price features block (priority #3), and a
     decision-history summary (last N decisions per cluster_key with stance and
     outcome).
   - GUI: a `REVIEW PACKET` panel in the existing `PACKET` tab showing the
     rendered packet pre-paste, so the user sees what the model will see.

3. **Rule-coverage gating on `ask-panel`** (extends priority #5).
   - Every position/market is tagged `rule_coverage ∈ {full, partial, missing}`
     based on presence of `rules_text_ref` and `oracle_type` in the registry.
     `missing` = neither present; `partial` = one present; `full` = both.
   - `ask-panel` (the Perplexity/Claude/ChatGPT subcommand from priority #5)
     **refuses to emit precise trade recommendations** — entry price, sizing,
     ladder placement — for any market with `rule_coverage="missing"` unless the
     user passes an explicit `--degraded-mode` flag. With the flag, the
     recommendation is allowed but stamped `degraded_mode: true` in its output
     JSON and surfaced amber in the GUI.
   - Every model suggestion carries a `strict_vs_fallback` block: what the
     recommendation is under strict-rule reading, what it would be under the
     fallback / disputed-resolution reading, and which one the model prefers and
     why. Forces the model to acknowledge wording risk explicitly rather than
     papering over it.

4. **Ladder cash model** (refines priority #2 cash-exposure bar).
   - Replace the naive "sum of all open buy `price × shares`" total with three
     buckets keyed off distance from the current mark (sourced from priority #3
     `features.json`):
     - `near_fill_exposure` — buys within ~3¢ of the mark. Realistically compete
       for cash; counted at full notional.
     - `mid_fill_exposure` — buys 3–10¢ away. Possible competition; counted at
       partial weight.
     - `deep_dislocation_exposure` — buys >10¢ away. Speculative ladder rungs;
       reported separately and **not** counted against available cash.
   - Per-rung `likely_cancel_or_unfunded: bool` flag is set only on near/mid
     orders that, summed, exceed cash on hand — a signal that something will
     have to give. Deep-dislocation rungs never carry this flag (the assumption
     that they fill is what dislocation means).
   - GUI: `<CashCommitmentBar>` renders three stacked segments (cyan / amber /
     dim) instead of a single bar, with the overage label only counting near+mid.

5. **Model disagreement log.**
   - When `ask-panel --mode adversarial` (Claude + ChatGPT in parallel) or `full`
     (all three sensors) runs, also emit a normalized
     `reports/generated/disagreement/<as_of>.json` keyed by `cluster_key`. Per
     cluster: `stance_disagreement` (do the models recommend different sides?),
     `reasoning_tag_disagreement` (do they cite different drivers?),
     `confidence_gap` (numeric delta), `missing_data_deltas` (what one model
     flagged as missing that the other didn't).
   - Decision-history summary in the review packet (deliverable #2) reads from
     this log so the model can see "you and the other sensor disagreed last time;
     here's why" before producing the next recommendation.
   - GUI: a small `DISAGREEMENT` chip on each cluster row in the `MARKETS` tab
     when the latest log entry shows non-trivial disagreement; click drills into
     the per-cluster JSON.

6. **Decision logging.**
   - Each `build-trade-ticket` run appends a row to
     `reports/generated/decisions/log.jsonl`: `{as_of, cluster_key, market_id,
     side, price, shares, source_state_hash, stale_flags, rule_coverage,
     degraded_mode, model_outputs_refs, adjudicator_ref}`. Append-only; the
     decision-history summary in the review packet reads from this log.
   - Distinct from priority #7's "anti-leak guardrails" — those *block* bad
     trades; this just *records* every decision so future review can ask "are
     we improving?" without re-deriving from scratch.

**Hard non-goals** (the brief proposed these; declining all):
- No three-session sequencing as written. Polyberg's roadmap is interleaved by
  priority, not gated by session phases. Each deliverable here is independently
  shippable.
- No `examples/iran-2026/` migration. `context/` stays canonical and user-owned.
- No FastAPI / Vite / SPA-from-FastAPI. All endpoints land as Electron IPC.
- No EOA private key handling whatsoever. The `derive_clob_creds.py` reference
  in the brief is moot — polyberg's CLOB credentials come from
  `POLYMARKET_*` env vars set by the user out-of-band; the project never sees
  the private key. This boundary stays absolute.

**Relationship to other priorities:**
- Schema versioning + raw-payload preservation is a **prerequisite** for #3
  (price collectors must be raw-first from day one), #5 (Perplexity cache),
  and #6 (state diff needs reproducible inputs).
- Review-packet preview consumes price features (#3) + ladder cash model (#4
  here) + decision history (#6 here) + disagreement log (#5 here). Build the
  inputs first, the preview last.
- Rule-coverage gating ties directly to the `rule_risk` field already in the
  registry; treat `rule_coverage` as a stricter machine-readable companion.

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
- **Telegram bot for notifications**: low priority, would be nice. One-way
  outbound notifications from polyberg to a private Telegram chat — never
  inbound commands, to preserve the no-execution safety boundary. Events to
  surface: limit buy/sell order fills (detected by diffing successive
  `import-public-positions` snapshots — a position's `size` jumping from N to
  N+25 with an open buy at the matching price implies that buy filled);
  major mark moves (5%+ in a window, leveraging the price-history pipeline
  from priority #3); kill-switch / churn flag trips once those land in
  priority #7. Implementation sketch: new CLI subcommand `notify-telegram`
  that takes a message body and posts via the Bot API
  (`api.telegram.org/bot<TOKEN>/sendMessage`). Bot token + chat id in
  `.env`, never committed; created via BotFather. A small Python watcher
  (cron or systemd timer locally) runs `notify-telegram` after each
  `import-public-positions` + `fetch-price-history` pass to evaluate
  triggers. The bot is *only* a transport — all detection logic stays in
  polyberg core so the same triggers can drive in-app GUI badges later.

### Other deferred work

- **Visual verification of ACCOUNT tab (P1a v1).** The new `AccountScreen`
  shipped with passing typecheck only — no one has actually opened the tab in
  the Electron dev server yet. Things to eyeball on first run: tab activates,
  empty-state shows when `reports/generated/account/` is empty, JSON pane
  pretty-prints, canonical YAML pane renders, the disabled PROMOTE button
  doesn't accidentally fire, side-by-side grid wraps reasonably on narrow
  windows. After running `$ import-account-snapshot` (even against the
  PM-US stub), confirm the file shows up live without an app restart.
- Cosmetic stubs still no-op: search bar (⌘K), filter buttons.
- `recent_catalysts.md` could be restructured to per-market sections so the catalyst
  timeline on each tab has data; today the file is section-based and the GUI shows
  empty timelines.
- Workflow-stage detection in `readContext.ts` probes guessed filenames in
  `reports/generated/` (`packet.md`, `model_a_validation.txt`, etc.) — tighten once
  the report layout stabilizes.
- **Intake tweet paste auto-format.** When a user pastes a tweet into the
  IntakeScreen textarea, detect the X/Twitter copy-paste shape and auto-populate
  the structured fields rather than leaving everything as raw body text. Concrete
  format (from a real paste):

  ```
  BREAKING: Iran responds to the US with a "10-point" message …

  1. US military presence …
  …

  2:21 PM · May 10, 2026
  ·
  86.6K
   
  Views
  ```

  Parse rules:
    - Trailing `H:MM AM/PM · Month D, YYYY` line → ISO timestamp into the author /
      timestamp field. Strip from the body.
    - Trailing `Views` / `NN.NK` view-count block → strip from the body (not stored).
    - `@handle` either at the start of the paste or in the author input → populate
      author with the leading `@`. When the handle is *not* in the paste (X often
      omits it from the body when copying just the tweet), prompt the user to fill
      it; don't silently leave it blank since downstream catalyst entries lose
      provenance without it.
    - Body becomes the cleaned tweet text. Preserve numbered list formatting
      (`1.`, `2.`, …) so it lands legibly in `recent_catalysts.md`.
  - Trigger: detect on paste event, not on every keystroke. Show a small "tweet
    detected — auto-formatted" hint with an UNDO affordance so a misdetected paste
    can be reverted to raw text.
  - Fallback: if the regex doesn't match the X shape, leave the textarea alone —
    the existing free-text behavior is the correct path for non-tweet sources.

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
