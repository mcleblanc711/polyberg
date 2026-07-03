# Interface Contract

Pinned on-disk artifacts consumed across sessions and (eventually) across
repos. **Do not change the shape of anything documented here without updating
this file in the same PR** (see CLAUDE.md). `decision_export.json` will be
added to this contract when it lands.

## canonical_session.json — `polyberg_session_v1`

The canonical artifact of every packet build. One session dir per
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
