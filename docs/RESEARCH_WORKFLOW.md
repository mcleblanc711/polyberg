# Public market research workflow

Install with `python -m pip install -e '.[dev]'`. Research needs no `.env`, wallet, exchange account, database server or model API key. To run the legacy authentication tests or use optional US account imports, additionally install `.[legacy]`.

## Start and discover

```bash
python -m polyberg.cli research init
python -m polyberg.cli research search "your subject"
python -m polyberg.cli research inspect https://polymarket.com/event/EVENT-SLUG
python -m polyberg.cli research follow https://polymarket.com/event/EVENT-SLUG
python -m polyberg.cli research follow https://polymarket.com/event/EVENT-SLUG/CHILD-MARKET-SLUG
python -m polyberg.cli research list
```

`search` and `inspect` return public allowlisted metadata; following also collects current public quotes and persists rules. Identifiers accepted by inspect/follow:

| Input | Meaning |
| --- | --- |
| `https://polymarket.com/event/<slug>` | Every child contract in the event |
| `https://polymarket.com/event/<slug>/<child-slug>` | One selected child; event membership is retained |
| `https://polymarket.com/market/<slug>` | One market |
| `<Gamma market ID>` or `market:<ID>` | Explicit Gamma market |
| `market:<slug>`, `event:<slug>`, `event:<ID>` | Explicit public object selection |
| `condition:0x<64 hexadecimal digits>` | Explicit condition ID lookup |
| `<slug>` or `slug:<slug>` | Check both market and event; ambiguous matches require explicit selection |

Only supported HTTPS Polymarket hosts and path shapes are accepted. A condition ID without `condition:` is rejected. Closed markets can be followed; unavailable books and rules are shown as missing, never filled from unrelated data. Use `search --include-closed` to include closed search results.

## Organize, refresh and investigate

Commands using `MARKET_ID` below expect the stored Gamma ID, not a legacy registry key.

```bash
python -m polyberg.cli research projects create "Weekly research"
python -m polyberg.cli research projects add "Weekly research" MARKET_ID
python -m polyberg.cli research list --project "Weekly research"
python -m polyberg.cli research status MARKET_ID researching
python -m polyberg.cli research tags MARKET_ID weekly shipping
python -m polyberg.cli research refresh --market MARKET_ID
python -m polyberg.cli research refresh --event EVENT_ID
python -m polyberg.cli research refresh --project "Weekly research"
python -m polyberg.cli research show MARKET_ID
python -m polyberg.cli research rules MARKET_ID
```

`refresh` without a selection updates followed, unarchived markets. Event refresh rechecks the complete child membership without refollowing previously unfollowed contracts. New children are saved as discovered research records. Public collection failure retains history and reports failed/partial retrievals. Every price component has its own retrieval time.

Statuses are `discovered`, `screening`, `researching`, `monitoring`, `rejected`, and `archived`. `unfollow MARKET_ID` removes the market from the default view while preserving history, notes and project memberships. `refollow`, `archive` and `unarchive` are explicit operations. `list --all` includes saved unfollowed/archived records. `history MARKET_ID` exposes workspace changes.

```bash
python -m polyberg.cli research note MARKET_ID "Published report observation" \
  --category observation --source https://example.org/report \
  --published-at 2026-10-26T12:00:00Z --observed-at 2026-10-26T15:00:00Z
python -m polyberg.cli research verify ENTRY_ID
python -m polyberg.cli research note MARKET_ID "How are revisions treated?" --category question
python -m polyberg.cli research annotate MARKET_ID "Established measurement period" \
  --version-id RULES_VERSION_ID --kind measurement_period --source-url https://example.org/rules
```

Entry categories: observation, evidence_summary, question, catalyst, hypothesis, scenario, contradiction, and model_interpretation. Repeat `--source` to attach several references. Publication, observation and entry timestamps remain distinct. Saving a note does not verify it. Only an observation with source references can be marked verified by the explicit `verify` action. This records the user's review, not automated factual verification. Model interpretations remain separate from rules and source evidence.

Rules annotations support conditions, oracle, resolution_source, fallback, ambiguity, dispute, measurement_period and resolution_deadline. They require a rules version and supporting source. Unknown annotations remain empty. Trading end dates do not imply resolution dates or weekly measurement periods.

## Relationships and comparison

```bash
python -m polyberg.cli research relate MARKET_ID OTHER_MARKET_ID "Explanation" --kind correlated
python -m polyberg.cli research relate MARKET_ID OTHER_MARKET_ID "Explicit logical argument" \
  --kind implication --source-url https://example.org/research
python -m polyberg.cli research compare MARKET_ID OTHER_MARKET_ID
```

Directed kinds are `implication`, `causal` and `prerequisite`, from the first market to the second. Symmetric kinds are `related`, `same_topic`, `correlated`, `mutually_exclusive`, `exhaustive`, `complementary`, `overlapping`, `alternative_deadline` and `same_measurement`. Symmetric pairs are stored in sorted order, so reversing them does not duplicate a relationship. These are explicit user assertions, not inferred conclusions. Comparison returns a frozen research view of both contracts, with trading dates, established resolution deadlines/measurement periods, all outcome prices, freshness, rules versions, and relationship explanations.

## Build and reuse packets

```bash
python -m polyberg.cli packet build --market MARKET_ID
python -m polyberg.cli packet build --event EVENT_ID
python -m polyberg.cli packet build --project "Weekly research"
python -m polyberg.cli packet render PACKET_ID --output-dir /tmp/research-export
```

Without a selection, `packet build` uses followed, unarchived markets. Packets are built from saved data; refresh explicitly when needed. Event packets show every known child and outcome, including explicit placeholders/warnings for uncollected children. If the public event response itself is incomplete, that limit is shown.

Each complete export has `canonical.json`, `shared.md`, `gpt.md`, `claude.md`, and a final checksum manifest. GPT and Claude have identical shared evidence bodies and snapshot hashes; only their analysis instructions differ. `packet render` reuses the recorded generation time and threshold, so files are byte-identical. The default freshness threshold is 36 hours, configurable with `POLYBERG_MAX_CONTEXT_AGE_HOURS`. Missing, invalid, future and stale retrieval timestamps produce warnings. Read the full [research interface contract](INTERFACE_CONTRACT.md).

Use `--db PATH` before the namespace or after the research/packet subcommand, or set `POLYBERG_RESEARCH_DB`. `--output-dir` changes only new research exports. Neither option imports legacy files.

## Desktop

From `gui/`, run `npm ci` and `npm run dev`. The app opens **Market research**, showing followed markets or an empty-state prompt. Search public events, follow one contract or the entire event, filter by project, and use **All saved** to recover unfollowed/archived research. The detail tabs expose outcomes, timestamps, identifiers, rules/history, sourced annotations, categorized research, explicit relationships/comparison, and frozen exports. The export tab supports contract, event, current project, or followed-market scope; all four files are written locally and the selected representation can be copied to the clipboard.

**Legacy portfolio** is an explicit selection. Its provider and screens load only then; failures stay in that workspace and the top-level switch remains available. Returning to research revokes legacy IPC access and stops the legacy watcher. Research watches only its configured database/sidecars and research export directory.

Previous CLI argument shapes remain available by adding `legacy`, for example `python -m polyberg.cli legacy packet build --target all`. Only this namespace loads repository dotenv credentials and legacy account implementations. See [legacy account documentation](account_connection.md).

Three [synthetic example handoffs](../examples/research/README.md) demonstrate one contract, related contracts with multiple deadlines, and a multi-contract weekly distribution with an unavailable price. They are never imported into your workspace.
