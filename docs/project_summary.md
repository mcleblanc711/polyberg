# Polyberg Project Summary

Last reviewed: 2026-05-08

## Purpose

Polyberg is a local-first Python research workbench for structured Polymarket analysis. It
turns manually maintained market, portfolio, order, catalyst, and rule context into repeatable
markdown packets for LLM review, validates model/adjudicator JSON against strict schemas, and
renders a human trade ticket from validated adjudicator output.

The project is intentionally not an automated trading system. Its safety posture is that every
model recommendation is untrusted until validated, and every final order still requires manual
human review and manual execution outside this repo.

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
