# TODO

## Next Session (priority)

- [ ] **Wire `build_market_snapshot`** (`src/polyberg/snapshots.py:47`) to real collectors in `src/polyberg/collectors/polymarket_clob.py` (`fetch_order_book`, `fetch_midpoint`, `fetch_spread`). Currently writes `None` for every price — biggest single quality win for the packet. Verify against a live market before declaring done.
- [ ] Decide on `iran_airspace_closed_may21` — resolution date passed 2026-05-21; either purge from registry or document why it stays as a historical reference.
- [ ] **Fix promote workflow → sample-data leak**: `pm promote-positions` / `pm promote-orders` (and the GUI PROMOTE button) write real state into the tracked `context/portfolio_current.yaml` and `context/open_orders.yaml`. The intent (per file comments) is that real state lives in `*.local.yaml` overlays. Either (a) add overlay-merge logic to the loaders like `live_state.local.yaml` already has and change promote to write to `.local.yaml`, or (b) document explicitly that the tracked files become real-state on local clones and accept the privacy implication. Until fixed, re-running PROMOTE on this machine will overwrite the sample data committed during 2026-05-23 cleanup.

## Bugs / Fixes

- [x] `tests/test_loaders.py::test_load_yaml_context_files` — `open_orders.sell_orders[0]` assertion fails when orders are empty; fixed during 2026-05-23 registry cleanup

## Features

- [ ] Intake screen "paste text tweets here" — format pasted tweet blobs: separate `@` handles, clean up RT prefixes, strip URLs or inline them, normalize whitespace so each tweet is a distinct readable line
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
