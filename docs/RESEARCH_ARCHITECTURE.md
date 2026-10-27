# Market-centric research architecture and isolation audit

The default CLI and desktop workspace use public market data and a new local SQLite database. No registry, portfolio, account cache, catalyst log, notes, `.env`, or session artifact is imported. The initial project is `default`, with zero markets. Existing files remain in place. Account work requires `polyberg legacy …` or explicit selection of **Legacy portfolio** in the desktop app.

## Boundaries

| Component | Role | Permitted inputs |
| --- | --- | --- |
| `polyberg.cli` | Default CLI and structured stdin RPC | Validated research requests, explicit database path |
| `research.public` | Discovery, identifiers, public normalization, prices, activity and on-demand depth | Gamma events/markets/search; CLOB public book, midpoint and last-trade endpoints; Data API v2 open interest |
| `research.history` | Outcome price history | Data API v2 `/v2/prices-history`; CLOB `/prices-history` fallback |
| `research.storage` | Python-owned SQLite access and numbered migrations | Validated research records |
| `research.workspace` | Follow, refresh, research entries, projects, rules and relationships | Research database and public client |
| `research.packets` | Freeze, render and publish packets | Explicitly allowlisted research records; persisted packet snapshots |
| `research.service` | Shared typed operation dispatch | Strict Pydantic request; no arbitrary command, path or legacy-stage field |
| `polyberg.http` | Shared GET-only transport | URLs, query parameters, caller-supplied headers |
| `polyberg.legacy_cli` | Previous CLI argument shapes and implementations | Legacy files and optionally authenticated services |
| Electron research IPC | Spawn a fixed Python namespace with JSON stdin | Validated operation allowlist; main-process database and export locations |
| React `ResearchProvider` | Default empty/followed-market workspace | Research IPC only |
| Lazy `LegacyWorkspace` | Previous portfolio UI | Legacy IPC after explicit per-window selection |

Research never imports account collectors, portfolio loaders, packet/session implementations, or authentication support. The existing Gamma and CLOB collectors import the neutral transport. `polymarket_account` re-exports the transport and error aliases for legacy callers. The previous `polyberg_session_v1` implementation and schema remain unchanged.

## Account inventory and exposure paths

This inventory names paths and roles without reproducing account identifiers or values.

| Existing surface | Account coupling or exposure | Research treatment |
| --- | --- | --- |
| `.env`; CLOB/Polymarket environment variables | Authenticated account reads and cancellation support | Dotenv loads only in legacy; known credential variables removed from research subprocess environment |
| `collectors/polymarket_account.py` | Public personal-position queries; US account snapshots; optional Ed25519 support | No imports or calls from research |
| `collectors/polymarket_clob_auth.py`, `_orders.py`, `_balance.py` | Authenticated balances and open orders | Legacy only |
| `account_normalizer.py`, `paste_import.py`, `loaders.py` | Portfolio, account and order normalization; local overlays | Not imported by research |
| `context/*local*`; `portfolio_current.yaml`, `open_orders.yaml`, `live_state.yaml` | Holdings, cash, watchlists and account state | Never read or migrated by research |
| `live/order_books.*`, `token_map.json`, `session_starter.md` | Resting-order annotations and generated account context | Never read; research fetches public prices independently |
| `live/order_log.jsonl`; ladder targets and execution modules | Order IDs, historical activity and existing cancellation behavior | Isolated legacy features; no new action subsystem |
| `reports/generated/account/` and decision inputs | Raw account caches and pasted model responses | Excluded from research reads and watchers |
| `reports/sessions/`, `latest_session.txt` | Legacy canonical raw account inputs | Separate contract and directories; never a research source |
| Legacy prompts, catalyst logs and screenshots | Can contain account interpretation or private notes | Not included in research exports or examples |
| Account-import test fixture | Previously copied account-shaped sample | Entire payload replaced with deterministic invented data |
| Default legacy tests | Could consume local overlays or changing registry IDs | Two failing assumptions replaced by temporary synthetic context; dual-packet tests use that context |

User-authored research text is preserved, so users control what they write into their own notes and source references. The isolation guarantee excludes upstream *unknown fields* and all legacy sources; it is not a claim that arbitrary user prose can be automatically classified as private.

## Public data decisions

Public identifiers remain distinct: event ID, Gamma market ID, condition ID, question ID, outcome index/ID, CTF token ID, and V2 position/asset ID. Following a single market also retrieves its public parent membership when available, so an event export can identify uncollected siblings. Outcome IDs use `<Gamma market ID>:<public outcome index>`. Labels are retained verbatim and never coerced into YES/NO. Parallel label, price and identifier arrays are joined by their documented indices. V2 selects `positionIds` only when `version` is `v2`; absent V2 IDs do not fall back to CTF IDs. Unsupported versions leave assets unavailable. Pre-versioned responses with explicit CTF arrays are recognized as legacy CTF data. See the [official identifier documentation](https://docs.polymarket.com/market-data/market-details).

Displayed prices, best bid, best ask, midpoint, and last trade are independent fields. The collector visits each available outcome asset. Best bid uses `max`; best ask uses `min`, without depending on book ordering. Missing prices stay missing; incomplete distributions are never rescaled and complementary prices are never manufactured. See the [official pricing documentation](https://docs.polymarket.com/market-data/prices-order-books).

Market `description` is preserved byte-for-byte as a Python string, with a SHA-256 of its UTF-8 representation. Event descriptions remain separate. The collector never invents rules or substitutes event text. Rules and displayed quotes record the actual supplying API URL, including when market data came from an event response. Rules versions include source URLs and established public resolution source/status; retrieval observations retain every successful observation, including unavailable rules. Identical rules versions deduplicate. Changes flag prior annotations for review. Annotation kinds cover conditions, oracle, resolution source, fallback, ambiguity, dispute, measurement period and resolution deadline. Unknowns stay empty. Trading start/end values are explicitly labelled trading dates.

Market activity uses only allowlisted Gamma figures from the payload a refresh already fetches, plus one batched open-interest read. Values that are missing or out of range stay missing. Price history is validated point by point; malformed points are dropped with a warning. The series served is the latest successful retrieval, and its supplying URL is recorded. Book depth is a read-only live view: levels are sorted by price, the top 10 per side are kept, and nothing is stored. The book's market-wide `last_trade_price` is not attributed to an outcome. All viewer data travels in separate models and response keys outside `ResearchPacket`.

Network requests finish before transactional writes. Metadata failure records a failed attempt and preserves the last snapshot and successful retrieval time. Component failures retain historical quotes only for matching outcome assets, with their original retrieval timestamps and explicit warnings. A valid empty book replaces the old book with unavailable best quotes; it does not resurrect old liquidity.

## Dependencies

| Layer | Dependencies | Account requirement |
| --- | --- | --- |
| Research persistence and network | Python standard-library `sqlite3`, `urllib`, hashing, JSON and UTC datetime | None; no database service or HTTP SDK |
| Contracts | Pydantic 2 and JSON Schema validation | None |
| Existing compatibility | PyYAML, RFC3339 validator, Windows tzdata | No account dependency; legacy YAML support retained |
| Optional legacy extra | `cryptography>=42` | US authenticated snapshot signing only; lazy import |
| Desktop | Electron, React/React DOM, chokidar, existing TypeScript/Vite toolchain | Research uses public IPC; `js-yaml` remains for the lazy legacy workspace |
| Verification | pytest, Ruff, Vitest, TypeScript | CI installs the legacy extra to exercise existing authentication tests |

No server, model-provider SDK, forecasting engine, trading subsystem, or database dependency was added. There is no change to existing legacy cancellation semantics.

## Verification scope and limits

Hermetic tests use invented market data and deny account imports and dotenv loading in a fresh process. They cover URL host/path parsing, child-contract selection, typed condition IDs, arbitrary outcomes, V2 assets, distributions, unsorted/malformed books, failed and partial refreshes, preserved timestamps, rules changes, sourced verification, archive history, project memberships, relationships, migration rollback, strict schemas, deterministic rendering and incomplete exports. Nested account-field injection sentinels are checked against storage, all exports and diagnostics. GUI tests exercise request rejection, fixed subprocess arguments, credential removal, isolated watchers, workspace access and empty startup. CI runs Python tests/lint and GUI tests/typecheck/build.

Evidence verification remains a manual user action supported by references; it does not independently confirm the source claim. Rules depend on public-source availability. SQLite is local, single-user storage. Refresh and model handoffs are manual. Follow-up priorities: richer source capture, scheduled public refresh, and optional quantitative-analysis inputs.
