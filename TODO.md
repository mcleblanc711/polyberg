# TODO

## Next Session (priority)

- [ ] **Wire `build_market_snapshot`** (`src/polyberg/snapshots.py:47`) to real collectors in `src/polyberg/collectors/polymarket_clob.py` (`fetch_order_book`, `fetch_midpoint`, `fetch_spread`). Currently writes `None` for every price — biggest single quality win for the packet. Verify against a live market before declaring done.
- [ ] Decide on `iran_airspace_closed_may21` — resolution date passed 2026-05-21; either purge from registry or document why it stays as a historical reference.
- [x] **Fix promote workflow → sample-data leak** (option a, 2026-05-31): promote (`promote-positions`/`promote-orders`/`promote-balance`/`paste-import`, CLI defaults + GUI PROMOTE) now writes to the gitignored `*.local.yaml` overlays. CLI loaders (`loaders.prefer_local_overlay`) and the GUI (`repo.contextFile`, used by `readContext` reads, `writers` draft-order writes, and freshness) prefer the overlay when present and fall back to the tracked sample. Tracked `portfolio_current.yaml`/`open_orders.yaml` stay sample-only. Real state from this machine was moved into the overlays during the fix.

## Bugs / Fixes

- [x] `tests/test_loaders.py::test_load_yaml_context_files` — `open_orders.sell_orders[0]` assertion fails when orders are empty; fixed during 2026-05-23 registry cleanup

## Features

- [x] **Intake screen tweet auto-parser** — parse pasted tweets in standard X format: extract author name, `@handle`, timestamp (e.g. "1m"), tweet text, and source line. Auto-populate the `author` field with the handle (with `@`), populate `text` with tweet content only (strip metadata lines and source line). Example parse:
  ```
  Mario Nawfal
  @MarioNawfal
  ·
  1m
  [tweet content here]
  
  Source: CBS News
  ```
  → author: `@MarioNawfal`, text: `[tweet content here]`. Handle both multi-line tweet content and bulletpoint summaries. Gracefully fall back to manual entry if parse fails.
  - [x] Pure parser implemented: `gui/src/shared/tweetParser.ts` (`parseTweetPaste`), forgiving — keeps unclassified lines as body, returns `parsed: false` for manual fallback.
  - [x] Wired into `IntakeScreen.tsx`: an `onPaste` handler on the tweet textarea auto-fills the author with `@handle` and the body with the cleaned text, stripping metadata/source lines; shows a parse hint and falls back to manual entry on no-match. `npm run typecheck` clean.
  - [ ] Optional follow-up: a JS test runner (vitest) so `parseTweetPaste` gets unit coverage — none is configured today (parser logic was verified out-of-band during implementation).
- [ ] Evaluate n8n integration — automate daily packet push to Claude Web and/or ChatGPT (assess feasibility: n8n HTTP nodes, headless browser vs API, scheduling, output retrieval)
- [ ] **Packet output format redesign** (from Claude Web project instructions review):
  - DROP: "Model Instructions" block, "Stable Trading Principles" block, dev scaffolding text, duplicate "Unresolved/Missing Information" section
  - DROP from Live State: `active_thesis` and `constraints` fields (static config, not live state)
  - ADD: "Session Focus" section after freshness audit — populated from optional `session_focus` input string
  - CHANGE: Catalyst section → markdown table with columns: Timestamp (UTC) | Source | Signal | Flag; add credibility key line (`* = high-signal · no mark = standard · ~ = noisy/rumour`)
  - CHANGE: "Trader Interpretation Notes" → "Session Interpretation"; populated from optional `session_interpretation` input string
  - CHANGE: Market Registry table — drop "Rule key" and "Resolution" columns; keep Market ID | Name | Preferred Side | Oracle | Rule Risk | Risk Flags
  - ADD: Market Snapshot table — add Bid | Ask | Volume | As Of columns if not present
  - Output-formatting changes only; no data-fetching or calculation logic changes
