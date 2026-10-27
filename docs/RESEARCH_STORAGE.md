# Research storage and migrations

The default path is `data/research/research.sqlite3`. Set `POLYBERG_RESEARCH_DB` or pass `--db PATH`; an explicit flag wins. Research databases, sidecars and `reports/research/` exports are gitignored. No existing YAML/JSON file is imported, renamed, removed or modified.

Python owns every database connection. Electron never opens SQLite: it spawns `python -m polyberg.cli --db <main-process path> research rpc`, passes a strict JSON request on stdin and receives JSON on stdout. Renderer requests cannot change the database path, supply shell commands, choose legacy stages or read arbitrary artifacts.

## Schema 1

`research/storage.py` defines numbered SQL migrations. On open the application reads `PRAGMA user_version`, rejects unsupported future versions, and applies pending migrations under a single `BEGIN IMMEDIATE` transaction. DDL, version updates and default-project creation commit together; an error rolls all of them back. Migration statements are recognized with SQLite's `complete_statement`, including trigger bodies. Normal reopen operations do not write to storage.

Every connection enables foreign keys and a 5,000 ms busy timeout. All application timestamps use UTC with an explicit offset. User source publication and observation timestamps retain their original, timezone-qualified values. Raw upstream date fields are preserved separately and never silently interpreted as rules deadlines.

| Tables | Records |
| --- | --- |
| `events`, `markets`, `outcomes` | Stable public identities, lifecycle, research status, follow state and explicit outcomes |
| `refresh_attempts`, `market_snapshots`, `outcome_quotes` | Successful, partial or failed refreshes; immutable snapshots and component quotes |
| `rules_versions`, `rules_observations`, `rules_annotations` | Verbatim versioned rules, observations (including unavailable rules) and sourced annotations tied to versions |
| `projects`, `project_markets`, `tags` | Default/named projects, memberships and market tags |
| `research_entries`, `sources`, `entry_sources` | Categorized entries and source provenance; explicit observation verification |
| `relationships` | Explicit directed or symmetric market pairs and explanations |
| `workspace_history` | Follow, status, membership, tag, note and verification actions |
| `packet_snapshots`, `exports` | Frozen packet input and completed export records |

JSON columns store validated allowlisted objects for immutable views; no raw API or legacy payload is stored. Append-only tables have SQLite triggers rejecting updates/deletes. Market metadata and outcome identities can advance; each historical snapshot retains the identification observed at its retrieval. Notes and memberships remain when a market is unfollowed or archived. Repeated archive is idempotent; unarchive restores the previous status.

Rules deduplication hashes the full allowlisted rules version, including source URLs and established resolution metadata. `text_sha256` separately hashes only the verbatim text. Old versions and annotations remain available after text changes or a later unavailable response. Earlier annotations are flagged for review, never silently applied to a changed version.

## Schema 2

Migration 2 adds two tables. Databases at schema 1 upgrade in place on the next open, and a failed upgrade rolls back to schema 1.

| Table | Records |
| --- | --- |
| `market_activity` | Allowlisted volume, liquidity, price-change, spread and open-interest figures, keyed to the snapshot they were collected with. Append-only, with immutable triggers |
| `price_history_fetches` | Latest validated price-history series per (outcome, span `1d`/`1w`/`1m`/`max`), with its supplying URL, retrieval time and warnings |

`price_history_fetches` is the one deliberate exception to append-only storage. It is a cache of public series that can be re-read: a successful fetch inserts the new row and deletes older rows for that outcome and span in the same transaction. Failed fetches write nothing. Neither table is read by packet building, so `polyberg_research_packet_v1` is unchanged.

## Backups and upgrades

For a consistent backup while the application is open, use SQLite's backup API or the `sqlite3 .backup` command. A simple file copy is suitable when all CLI and desktop processes using the database are closed. Keep backups and exported packets private according to the content of your own research notes.

Future migrations must be assigned the next schema number, retain previous migrations, and be covered by rollback/reopen tests. The application deliberately has no automatic downgrade, legacy-data migration or background database replacement. To experiment with a fresh workspace, choose a different `--db` path.

## Frozen exports

`packet_snapshots.data` stores the complete `polyberg_research_packet_v1` JSON, including one generation time and resolved freshness threshold. The packet ID and snapshot hash equal the SHA-256 of canonical UTF-8 JSON (sorted keys, two-space indentation, one trailing LF). Renderers read that persisted object; later environment settings, wall-clock changes or workspace edits cannot alter a repeated render.

Exports live under `reports/research/<packet_id>/` (or `<--output-dir>/<packet_id>/`). All four files are validated and rendered in memory, written into a sibling staging directory, followed by `manifest.json`, and published with a directory rename. The manifest maps the four allowlisted filenames to their exact byte hashes. `verify_export()` rejects missing manifests, missing/modified files, snapshot hash mismatches and content that differs from a deterministic render of the canonical snapshot. Existing incomplete destinations are rejected, not treated as complete or silently overwritten. The desktop returns rendered content only after export completion.
