# Polyberg Ladder Manager — Design (signed off 2026-06-10, not yet implemented)

Status: design approved by user; implementation deferred. Follow the
"Implementation order" section below; all sign-off decisions are recorded
and should not be re-litigated.

## Context
User manages exits via limit-sell ladders and entries via resting limit bids across many Polymarket markets, currently by hand in the UI — slow and error-prone during live catalysts. Build: declare target order state in a file → diff vs live open orders → human-reviewable reconciliation plan. Research/decision-support posture (stable_rules.md): tool proposes, human confirms, never decides. User just cancelled the entire book, so first real run is "empty live book → place full target". CLAUDE.md/AGENTS.md do not exist in repo (flagged); stable_rules.md read.

## USER SIGN-OFFS (AskUserQuestion, 2026-06-10)
- signature_type: env-driven via POLYMARKET_CLOB_SIGNATURE_TYPE, default 1 (no type 3 exists; type 1 verified working for this account).
- --execute v1: CANCELS ONLY (L2 HMAC DELETE) + pipe-delimited paste block for placements. No private key in repo. Placement walk still prompts "placed manually? [y/n/skip]" and logs it.
- File layout: tracked `live/target_ladders.yaml` commented sample + gitignored `live/target_ladders.local.yaml` overlay; `live/order_log.jsonl` gitignored.
- GUI: INCLUDE a Ladder tab in this build (plan view + per-action confirm).

## Key verified repo facts
- models.py: `Side = Literal["YES","NO"]` is the OUTCOME; BUY/SELL encoded by list membership in OpenOrders. Order enforces order_type=="limit". StrictModel = extra:forbid pydantic v2.
- Auth: `collectors/polymarket_clob_auth.py` — ClobCredentials (env POLYMARKET_CLOB_*), `build_hmac_signature` (supports any method+body), `build_level_2_headers` (GET-only guard, line ~155 — do not touch). `ReadOnlyHttpClient` (collectors/polymarket_account.py) GET-only by design.
- Open orders: `collectors/polymarket_clob_orders.py` `fetch_open_orders()` paginated GET /data/orders; raw fields id, market(condition_id), asset_id, side BUY/SELL, outcome, price, original_size, size_matched. Artifact via `write_clob_open_orders` (payload-keyed JSON) — reuse as --live-from seam.
- Balance: `collectors/polymarket_clob_balance.py` GET /balance-allowance, `balance_to_decimal_usdc`; GET /balance-allowance/update is a GET → works with read-only stack.
- Loaders: `parse_model`, `prefer_local_overlay` (loaders.py:55), `repo_path` (config.py). Registry: condition_id, yes/no_token_id, band_verified, rule_risk.media_fallback.
- CLI: argparse, `command_<name>(args)->int`, nested group pattern exists (`packet build`). Tables: plain markdown pipe tables (renderers/tables.py). Tests: per-file FakeResponse/ScriptedOpener injected via opener=/http=, tmp_path fixtures, no conftest.
- .gitignore has context/*.local.yaml; needs live/ entries.

## Design (Plan agent, accepted)

### Module layout
```
src/polyberg/ladder/
    __init__.py      # public API re-exports
    models.py        # TargetLadders schema + load_target_ladders()
    live_orders.py   # raw CLOB orders -> LiveRung list via registry token index
    diff.py          # pure: targets + live -> LadderPlan
    validate.py      # hard validators + warnings; LadderValidationError
    render.py        # markdown plan table + pipe paste block + warnings
    executor.py      # execute walk, y/n confirm, order_log.jsonl appender
    clob_cancel.py   # MutatingClobClient (DELETE /order only) + non-GET L2 headers
live/target_ladders.yaml          # tracked commented seed (1 sell + 1 buy ladder)
live/target_ladders.local.yaml    # gitignored real state (overlay wins)
live/order_log.jsonl              # gitignored
tests/test_ladder_{models,diff,validate,render,cli,executor}.py
```
CLI wiring in existing cli.py. Ladder imports only models/loaders/config + 3 collector modules; zero packet_builder coupling.

### YAML schema (ladder/models.py, StrictModel)
- `Action = Literal["BUY","SELL"]`; `Purpose = Literal["cash_rebuild","derisk","runner"]`; outcome reuses `Side`.
- Rung{price: float gt=0 lt=1, shares: float gt=0}. NO order_type field anywhere → market orders structurally unrepresentable (extra=forbid rejects `order_type: market`).
- Ladder{market_id, outcome, action, rungs(min 1), tags{purpose?, notes}?} + validator: no duplicate rung prices.
- MatchingConfig{price_tolerance=0.0005 (half-tick), shares_tolerance=1.0 abs} in top-level `matching:`; CLI flags override.
- TargetLadders{schema_version="1", matching, ladders}.
- `load_target_ladders(path=None)`: prefer_local_overlay(live/target_ladders.yaml) → parse_model → hard fail on unknown market_id or missing token_id for declared outcome.

### Live normalization (live_orders.py)
- `build_token_index(registry) -> {asset_id: (market_id, outcome)}`; primary match on asset_id, order's own outcome/market fields are cross-check (mismatch → raise).
- LiveRung{order_id, market_id, outcome, action, price, original_size, size_matched, remaining=orig-matched}; drop remaining<=0.
- Unresolvable orders → UnmappedOrder list — NEVER cancelled, rendered in "unmanaged (not in registry)" section.
- Sources: live `fetch_open_orders()` or `--live-from FILE` (import-clob-orders artifact).

### Diff (diff.py, pure)
- Managed keys = (market_id, outcome, action) triples in target. Default: live orders outside managed keys → `unmanaged` (untouched). `--manage-all` → cancel them (reason=not_in_target).
- Per key: greedy one-to-one nearest-price matching within price_tolerance.
- Matched: |remaining - target.shares| <= shares_tolerance → keep; else cancel(reason=shares_mismatch, replacement=PlaceAction) + place. Partial fills compared on REMAINING.
- Unmatched target rung → place; unmatched live rung on managed key → cancel.
- Pre-flight: whenever plan.place non-empty, prepend step "GET /balance-allowance/update — required after any position close before new orders accepted" (always-on when placing: cheap idempotent GET; can't reliably detect closes).
- Deterministic ordering: sort all lists by (market_id, outcome, action, price).
- LadderPlan{preflight, cancel, place, keep, unmanaged, unmapped, warnings}.

### Validators (validate.py) — validate BEFORE diff; collect all, raise once
HARD (LadderValidationError, no plan emitted):
1. Limit-only — structural via schema (test pins unrepresentability).
2. `[sell-cap]` SELL rung price > 0.96 → fail w/ message (0.96 exactly passes).
3. Registry integrity: unknown market_id, missing token id, in-tolerance duplicate rungs.
WARN (non-blocking):
- `[cash-collision]` Decimal sum(price*shares) over ALL BUY rungs > available_cash → warn showing worst-case, cash, overage. Not hard: only downside of overcommit is the exchange cancelling unfunded orders if all rungs fill.
- `[dirty-oracle]` BUY ladder on market with band_verified=false OR rule_risk.media_fallback=true (fill-inversion).
- `[stale-cash]` when cash came from portfolio_current.yaml instead of live balance read.
Cash resolution: --cash flag > live fetch_collateral_balance > portfolio cash_available (+warn).

### Render (render.py)
- Markdown pipe table: | # | Action | Market | Outcome | Side | Price | Shares | Reason/Purpose |, grouped CANCEL/PLACE/KEEP/UNMANAGED.
- Paste block: header + pre-flight line + `CANCEL|market|outcome|side|price|shares|order_id=...|url` and `PLACE|market|outcome|side|price|shares|limit|url` lines.

### Executor (executor.py + clob_cancel.py)
- clob_cancel.py: `build_level_2_mutating_headers` (uses build_hmac_signature directly), `MutatingClobClient` (DELETE /order ONLY, separate class — ReadOnlyHttpClient invariant untouched), `cancel_order(creds, order_id, http=None)`.
- execute_plan(plan, creds, log_path, confirm=input, cancel_client=None, preflight_http=None, now=None) -> exit code. Per-action y/n; NO --yes bulk flag by design. Cancels via API; placements print paste line + "placed manually? [y/n/skip]". Pre-flight GET fired before first action when places exist.
- append_order_log: append-only jsonl, one object per ATTEMPTED action: {ts, action, market_id, outcome, side, price, shares, order_id, status: ok|http_error|declined|manual_confirmed|skipped, response_excerpt(300ch)}.
- `ladder execute` always builds+validates fresh plan in same invocation (no stale-plan-file execution).

### CLI
```
ladder plan    --target PATH --live-from FILE --cash X --price-tolerance --shares-tolerance --manage-all --paste/--no-paste
ladder execute (same) --log PATH(default live/order_log.jsonl)
```
Exit codes: 0 ok, 1 operational error, 2 validation hard-fail.

### Tests (per-file fake openers, tmp_path)
- test_ladder_models: parse ok; `order_type: market` rejected (limit-only pin); price/shares bounds; unknown market_id; dup rungs; .local overlay preferred.
- test_ladder_diff: EMPTY LIVE BOOK → full placement (user's first run); partial overlap; tolerance edges (in/out); shares mismatch → cancel+replace pair; partial fill on remaining; unmanaged untouched vs --manage-all; unmapped surfaced; deterministic order.
- test_ladder_validate: 0.961 fails w/ exact msg, 0.96 passes; cash collision cross-market w/ overage to cent; equal-cash passes; dirty-oracle WARN both triggers; multiple hard fails reported together.
- test_ladder_render: sections present; paste line format; pre-flight iff places.
- test_ladder_cli: --live-from end-to-end; empty book; validation fail → exit 2 no table; pre-flight in output.
- test_ladder_executor: y → DELETE w/ correct POLY_* headers+body, status=ok; n → no HTTP, declined; HTTP error logged, walk continues, exit nonzero; pre-flight GET before first action; manual_confirmed; jsonl shape.

### Implementation order
1. .gitignore + seed live/target_ladders.yaml
2. ladder/models.py + tests
3. live_orders.py
4. diff.py + tests
5. validate.py + tests
6. render.py + tests
7. CLI ladder plan + tests (offline first)
8. clob_cancel.py + executor.py + CLI ladder execute + tests
9. GUI Ladder tab (see below)
10. Docs touch (docs/account_connection.md: pre-flight rule + module note)

### Risks / verify during build
- DELETE /order body key (orderID vs orderId) + HMAC body serialization must byte-match py-clob-client reference (single-quote-replacement quirk in build_hmac_signature line ~138).
- /balance-allowance/update params/response — assumed same as /balance-allowance.
- Decimal for cash math (Decimal(str(x))); floats elsewhere.
- Selling-more-than-held check: out of scope, candidate future WARN.

## GUI Ladder tab (designed from GUI exploration)

GUI infra that already exists (reuse, don't rebuild):
- `gui/src/main/ipc/runStage.ts`: `runStage(name, args)` / `runStageStream(...)` spawn `python -m polyberg.cli <name> ...` (cwd REPO_ROOT, .venv python); names gated by `ALLOWED_STAGES` in `gui/src/shared/contract.ts`. Result {ok, code, stdout, stderr}.
- Preload: `window.pm.runStage` / `runStageStream` already exposed — no new preload methods needed for stage runs.
- Patterns: StageRunnerModal (streaming output), PromotePreviewModal in AccountScreen.tsx:326 (confirm modal, Escape/backdrop cancel), inline CSSProperties styling with tokens.ts (C.*, F.*, clipCard), `S: Record<string, CSSProperties>` per screen, warnings in amber `S.warn` boxes, tabs via ScreenId union + tabs array in App.tsx.

CLI additions to support GUI (small, keeps all auth/logic in Python):
- `ladder plan --json` → print machine-readable LadderPlan JSON (actions get stable indices; includes preflight, warnings, paste lines per action).
- `ladder cancel --order-id X [--log PATH]` → single non-interactive cancel + jsonl log (confirmation happens in GUI modal; one action per invocation preserves per-action human confirm).
- `ladder preflight` → fire GET /balance-allowance/update, print result (GUI button).
- `ladder record-manual --market ID --outcome O --side S --price P --shares N [--log PATH]` → append manual_confirmed jsonl entry when user marks a PLACE as done in GUI.

GUI changes:
- contract.ts: add 'ladder' to ALLOWED_STAGES (subcommand+flags ride in args, like 'packet').
- App.tsx: add 'ladder' to ScreenId union + LADDER tab.
- New `gui/src/renderer/src/screens/ladder/LadderScreen.tsx`:
  - "BUILD PLAN ▸" → runStageStream('ladder', ['plan','--json']) → parse stdout JSON; exit 2 → render hard-fail banner (red) with messages, no plan; warnings → amber box.
  - Plan rendered as grouped sections CANCEL / PLACE / KEEP / UNMANAGED; pre-flight banner with "RUN PRE-FLIGHT ▸" button (ladder preflight).
  - CANCEL rows: "CANCEL ORDER ▸" → confirm modal (PromotePreviewModal pattern, shows market/outcome/side/price/shares/order_id) → on confirm runStage('ladder', ['cancel','--order-id',id]) → row state executed/error from exit code; refresh plan after.
  - PLACE rows: copy-paste-line button (clipboard) + "MARK PLACED" → confirm modal → ladder record-manual.
  - No bulk-approve button anywhere (mirrors CLI: no --yes).
- Error surfacing: stderr shown in modal (red) per StageRunnerModal convention.

## Seed file sketch (tracked live/target_ladders.yaml)
schema_version "1"; matching{price_tolerance 0.0005, shares_tolerance 1.0}; one SELL ladder (hormuz_normal_end_june NO: 0.90×150, 0.94×100, purpose cash_rebuild) + one BUY ladder (hormuz_normal_jul31 NO: 0.72×200, purpose runner); comments explaining limit-only, 0.96 cap, cash-collision rule, .local overlay.
