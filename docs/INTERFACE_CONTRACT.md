# Interface Contract

Pinned on-disk artifacts consumed across sessions and (eventually) across
repos. **Do not change the shape of anything documented here without updating
this file in the same PR** (see CLAUDE.md). `decision_export.json` will be
added to this contract when it lands.

## canonical.json — `polyberg_research_packet_v1`

Default producer: `polyberg packet build`. Models: `research/models.py`.
Schema: `schemas/research_packet.schema.json` (Draft 2020-12). Every object forbids unknown
fields. This is independent of the legacy session contract below and contains no raw API,
portfolio, account, order or legacy-artifact sections.

| Field | Meaning |
| --- | --- |
| `schema_version` | Literal `polyberg_research_packet_v1` |
| `generated_at` | Single persisted UTC generation/freshness anchor |
| `max_age_hours` | Resolved positive freshness threshold, default 36 |
| `selection` | Explicit market, event, project, or followed selection |
| `events` | Separate event identity, description, source URLs, expected child IDs and contract identities |
| `markets` | Allowlisted identity/all outcomes, lifecycle/research status, follow state, tags/projects, current immutable snapshot and component timestamps, verbatim versioned rules, annotations, research entries/sources and relationships |
| `warnings` | Selection/event completeness and freshness warnings; per-market and per-quote warnings remain with those records |

Missing market rules are `null`. Event descriptions never replace rules. Market rules retain
exact text, text SHA-256, API/page sources, first retrieval and all observations of that
version. `annotations_for_review` retains earlier sourced annotations after a rules change;
these are separate from the current rules version's established annotations. Outcome IDs
are `<Gamma market ID>:<public index>`; label, CTF token ID and V2 asset/position ID stay
separate. Displayed prices, bids, asks, midpoints and last trades are independent nullable
fields. Trading end is not a resolution deadline. Missing child snapshots are explicit.

The complete packet JSON is persisted before rendering. Its SHA-256 identifies the frozen
snapshot and export subdirectory. Repeated render reads the saved anchor, freshness threshold,
evidence, annotations and warnings without consulting the clock, environment, network or
live workspace. GPT and Claude instructions differ; the bytes between
`<!-- BEGIN SHARED EVIDENCE -->` and `<!-- END SHARED EVIDENCE -->` are identical to `shared.md`.
Both include the same snapshot hash. The JSON evidence block in shared Markdown equals
`canonical.json`.

```
reports/research/<packet_id>/
  canonical.json
  shared.md
  gpt.md
  claude.md
  manifest.json
```

`manifest.json` uses `polyberg_research_export_v1`, includes `packet_id`,
`snapshot_sha256`, and the four filename → UTF-8-byte-SHA-256 entries in `files`.
A sibling staging directory is populated and the manifest written last, then the complete
directory is renamed into place. Readers validate the manifest and all file hashes before
accepting an export. No legacy pointers or artifact names are used.

Desktop IPC uses the strict `research.service.Request` contract over JSON stdin. The
TypeScript allowlist is `gui/src/shared/research.ts`. Research requests cannot supply a
legacy stage, arbitrary subprocess argument, database path, output path or legacy artifact.
Database access and export verification belong to Python. Legacy IPC is gated on explicit
per-window workspace selection. Research watchers cover only research database/sidecars
and research exports.

## canonical_session.json — `polyberg_session_v1`

The canonical artifact of every **legacy** packet build. One session dir per
packet-producing CLI run:

```
reports/sessions/<session_id>/
  canonical_session.json     ← written first, after in-memory validation
  <packet artifacts>         ← rendered FROM the validated JSON
  manifest.json              ← written last; its presence marks completeness
reports/latest_session.txt   ← bare session_id of the newest complete session
```

Schema: `schemas/canonical_session.schema.json` (Draft 2020-12,
`additionalProperties: false`, all 20 top-level keys required). Validation
helpers: `polyberg.validators.validate_canonical_session_payload` (in-memory)
and `validate_canonical_session` (file). Producer models live in
`polyberg.packet_builder.session`.

### Key table

Raw sections store inputs verbatim; derived sections are recomputed from the
raw sections + `build_parameters` and are stored for audit/consumer
convenience only — they must never be treated as an independent source of
truth.

| Key | Kind | Contents |
|---|---|---|
| `schema_version` | const | `"polyberg_session_v1"` |
| `session_id` | id | `session_YYYY-MM-DD_HHMMSS` (+ optional `_N` collision suffix); always matches the dir name |
| `generated_at` | anchor | `state.now.isoformat()` — identical string to the packets' `packet_generated_at`; re-parsing it reproduces every rendered timestamp byte-exactly |
| `mode` | const | `"research_only"` (the session's own pin; `fresh_context.live_state.mode` is stored untouched) |
| `execution_allowed` | const | `false` |
| `operating_constraints` | derived | `no_market_orders` / `use_sell_ladders` / `avoid_99c_dispute_tax` (bools coerced with `is True`) + const `automated_execution: false`, `human_review_required: true` |
| `source_timestamps` | derived | as_of strings per source (nullable) + `static_reference` sub-object (null-valued entries when rules are embedded, `{}` otherwise) |
| `fresh_context` | **raw** | `{"live_state": <LiveState dump>}` |
| `static_reference` | **raw** | `{"trading_principles": <text>, "stable_rules": <text>}` when the run writes a rules artifact; `{}` otherwise |
| `portfolio` | **raw** | `Portfolio.model_dump(mode="json")` |
| `open_orders` | **raw** | `OpenOrders.model_dump(mode="json")` |
| `market_registry` | **raw** | full `MarketRegistry.model_dump(mode="json")`; packet trimming is re-derived |
| `order_books` | **raw** | `{"raw": <order_books.json dict or null>, "markdown": <order_books.md text or null>}` |
| `market_snapshot` | **raw** | `MarketSnapshot.model_dump(mode="json")`, or `{}` when the build ran without a snapshot |
| `catalysts` | **raw** | `{"markdown": <recent_catalysts.md text>}`; windowed watch lists are derived |
| `freshness_audit` | derived | `{"warnings": [...], "live_state_as_of": ...}` |
| `completeness_audit` | derived | `{"missing_info", "blocking_warnings", "priceable_markets", "unpriceable_markets"}` |
| `gate_status` | placeholder | `{}` — reserved for a later severity/gating pass |
| `exposure_summary` | derived | `{"by_thesis_bucket": [...], "is_fallback": bool, "concentration_warnings": [...]}` |
| `build_parameters` | **raw** | see below |

### `build_parameters` (why it exists)

Trim flags change derived content — the active set, catalyst window, and book
scope. Without them the JSON could not re-render its packets, so they are part
of the contract: `targets`, `include_resolved`, `catalyst_window_hours`
(resolved to a number), `books_for` (`active`/`all`), `type_filter`
(`{category, thesis_bucket, rule_key}` or null), `max_context_age_hours`
(resolved; **audit-only** — it is re-read from the environment at render
time), `context_dir`, `snapshot_path` (both null for default builds).

### Reconstruction guarantee

`packet_state_from_session(payload)` losslessly rebuilds the factual state
from the raw sections; `canonical_packet_from_session(payload)` re-derives the
full packet from it plus `build_parameters`. Production rendering uses exactly
this path — every artifact in a session dir was rendered from the validated
JSON, not from the in-memory objects that produced it — and round-trip tests
(`tests/test_canonical_session.py`) prove `render(from_json) ==
render(in_memory)` for the GPT, Claude, and legacy packets.

### Const invariants

`execution_allowed: false`, `mode: "research_only"`,
`operating_constraints.automated_execution: false`,
`operating_constraints.human_review_required: true` are pinned three ways: as
Pydantic `Literal` fields, as schema `const`s, and by construction (no
producer function takes a parameter that can set them —
`tests/test_canonical_session.py` asserts all three).

### Write ordering / failure semantics

Payload is validated **in memory before any file or dir exists**; a validation
failure has zero filesystem effects. Then: claim session dir → write
`canonical_session.json` → render artifacts from the payload → write
`manifest.json` → swap `latest_session.txt` (temp file + `os.replace`) → write
mirrors. There is no rollback: a session dir **without `manifest.json` is an
abandoned session** and consumers must ignore it; the previous pointer stays
intact.

Same-second runs claim `_2`, `_3`, … suffixed dirs (`mkdir(exist_ok=False)`
retry); the id inside the JSON and manifest always matches the final dir name.

## manifest.json

Schema: `schemas/session_manifest.schema.json`.
`{"session_id": ..., "created_at": <== generated_at>, "files": {<key>:
<session-dir-relative filename>}}`. `files` always contains
`"canonical_session": "canonical_session.json"`; the manifest itself is never
listed — manifest-written-last is the completeness marker.

## reports/latest_session.txt

The bare `session_id` plus a trailing newline — no paths, so the artifact is
relocatable. Consumers resolve `reports/sessions/<session_id>/` themselves and
should verify `manifest.json` exists before trusting the dir.

## Mirroring (transitional)

Each packet artifact is also written byte-identical to its pre-session output
location (`reports/generated/`, `dist/packets/`, or the `--output` path) so
the GUI and existing habits keep working. Mirrors are a compatibility shim:
once the GUI resolves `latest_session.txt`, mirroring will be deprecated —
treat the session dir as the source of truth.

## Versioning

Additive, backward-compatible changes (new optional structure inside
permissive sections) may keep `polyberg_session_v1`. Any breaking change —
removing/renaming a key, changing a type, tightening a const — requires
bumping to `polyberg_session_v2`, a new schema file, and a migration note
here.

## Privacy note

Sessions embed the full local context (real portfolio, proxy wallet via
`live_state`). `reports/sessions/**` and `reports/latest_session.txt` are
gitignored; keep identifying data in gitignored `*.local.yaml` overlays as
usual and never commit session dirs.
