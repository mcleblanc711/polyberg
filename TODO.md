# TODO

## Next Session (priority)

- [ ] **Verify `build_market_snapshot` against a live market.** Wiring to the live CLOB collectors is DONE (commit `22eaa6b`, 2026-05-30): `snapshots.py` calls `fetch_midpoint`/`fetch_order_book` and fills prices + `orderbook_depth_top` (the "Top depth" column in the packet). Only the live-market verification remains; the old "writes None for every price" description was stale.
- [ ] **Grok-4.3 tweet auto-compile → INTAKE queue** (planned, NOT started — gated on a spike). Decisions locked: handles-only watchlist in a gitignored `context/grok_watchlist.local.yaml`; results land in the existing INTAKE queue (reuse tag→`appendCatalyst` flow). Spike (`/tmp/grok_spike.py`, ready) must first confirm OpenRouter passes xAI `search_parameters`/`x_handles` through to live X search — blocked on `OPENROUTER_API_KEY` in `.env`. If passthrough fails, pivot to the xAI API directly. Build plan: new auth-aware POST module `collectors/grok_tweets.py` (the read-only `ReadOnlyHttpClient` is GET-only by design — do NOT extend it); CLI `collect-tweets`; IPC + "Pull from Grok" button on IntakeScreen; ≤10 handles per query (batch the watchlist). See memory [[feedback-grok-api]].
- [ ] Decide on `iran_airspace_closed_may21` — resolution date passed 2026-05-21; either purge from registry or document why it stays as a historical reference.
- [x] **Fix promote workflow → sample-data leak** (option a, 2026-05-31): promote (`promote-positions`/`promote-orders`/`promote-balance`/`paste-import`, CLI defaults + GUI PROMOTE) now writes to the gitignored `*.local.yaml` overlays. CLI loaders (`loaders.prefer_local_overlay`) and the GUI (`repo.contextFile`, used by `readContext` reads, `writers` draft-order writes, and freshness) prefer the overlay when present and fall back to the tracked sample. Tracked `portfolio_current.yaml`/`open_orders.yaml` stay sample-only. Real state from this machine was moved into the overlays during the fix.

## Bugs / Fixes

- [x] `tests/test_loaders.py::test_load_yaml_context_files` — `open_orders.sell_orders[0]` assertion fails when orders are empty; fixed during 2026-05-23 registry cleanup

## Features

- [x] **Add Market flow** (2026-06-07) — the dead `+ ADD MARKET` button on MarketsScreen now opens a modal that takes a Polymarket URL/slug, auto-fetches `condition_id` + both token IDs + name/resolution-date from Gamma (`registry-add --preview`), collects the judgment fields (market_id/category/rule_key/oracle_type/preferred_side/thesis_bucket/risk_flags/notes), and appends a validated entry to `market_registry.yaml` (`registry-add` commit). Backend: implemented real `fetch_event_by_slug`/`normalize_gamma_event` in `collectors/polymarket_gamma.py`, new `registry_editor.py` (slug parse, Gamma→Market merge, indent-aware append + re-parse guard, duplicate rejection), CLI `registry-add`, tests in `tests/test_registry_editor.py`. IDs-only auto-fill (no judgment-field defaults). Follow-ups: wire the per-row `EDIT` button (still a no-op; editing existing entries is unsupported), and optionally default-prefill judgment fields. Kills the recurring "missing token IDs" gap for new markets.
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
- [ ] **Archive aged catalysts/intakes out of the packet** — `context/recent_catalysts.md` (~198 lines and growing) is rendered in full into both packets (`parse_catalysts` → `catalyst_block` in the claude/gpt renderers), and the backlog is diluting LLM context. Move entries past a freshness cutoff out of the packet-facing file into a dated archive the packet builder ignores (e.g. `context/catalysts_archive.md` / `.jsonl`), keeping only the recent window inline. **Don't discard** the archived tweets/signals — retain timestamp, source, signal text, the market it bore on, and credibility tier so we can later **backtest signal accuracy** (did the catalyst actually move / correctly call the market?). Open questions: cutoff policy (age vs count vs per-section), manual vs automatic archival, and whether to snapshot the market mark *at intake time* so accuracy is measurable after the fact. Keep the GUI INTAKE queue as the entry point; archival is downstream of confirmation.
- [ ] **Packet output format redesign** (from Claude Web project instructions review):
  - DROP: "Model Instructions" block, "Stable Trading Principles" block, dev scaffolding text, duplicate "Unresolved/Missing Information" section
  - DROP from Live State: `active_thesis` and `constraints` fields (static config, not live state)
  - ADD: "Session Focus" section after freshness audit — populated from optional `session_focus` input string
  - CHANGE: Catalyst section → markdown table with columns: Timestamp (UTC) | Source | Signal | Flag; add credibility key line (`* = high-signal · no mark = standard · ~ = noisy/rumour`)
  - CHANGE: "Trader Interpretation Notes" → "Session Interpretation"; populated from optional `session_interpretation` input string
  - CHANGE: Market Registry table — drop "Rule key" and "Resolution" columns; keep Market ID | Name | Preferred Side | Oracle | Rule Risk | Risk Flags
  - ADD: Market Snapshot table — add Bid | Ask | Volume | As Of columns if not present
  - Output-formatting changes only; no data-fetching or calculation logic changes
