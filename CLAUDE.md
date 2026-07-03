# CLAUDE.md — polyberg

## What this repo is
Daily Polymarket research cockpit: session intake, state refresh, packet building,
model prompt rendering, adversarial review support, decision export. Research
tooling only — a human reviews everything and places all orders manually.

## Hard boundaries (never violate, regardless of task prompt)
- NO automated execution. NO market orders. NO order placement or cancellation.
- NO wallet or private-key handling. NO browser automation.
- NO new repos. NO circular dependencies (polyberg must not import polygraph/prophet).
- `execution_allowed` is always `false`. Do not add code paths that could flip it.
- Forbidden identifiers in src code: place_order, cancel_order, sign_order,
  private_key, market_order. (Docs/tests may reference them as forbidden.)

## Repo boundaries (do not absorb these)
- polyberg-polygraph owns: immutable fills, decision ledger, postmortems.
- polyberg-prophet owns: source/claim scoring against resolved outcomes.
- polyberg-core owns: shared enums/schemas — only once ≥2 repos consume them.

## Conventions
- Follow existing schema/model conventions in this repo (check before choosing
  Pydantic vs dataclass vs other).
- Interface artifacts (canonical_session.json, decision_export.json) are pinned
  contracts. Do not change their shape without updating docs/INTERFACE_CONTRACT.md.
- Work on a feature branch. Never commit directly to main.
- Tests accompany the change in the same PR, not after.

## Reporting format (end of every task)
Summary / Files changed / Tests run (with results) / Schema or interface changes /
Known risks / Suggested follow-ups. Do not claim success unless tests pass.
