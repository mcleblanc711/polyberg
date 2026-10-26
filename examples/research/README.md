# Guaranteed synthetic research packets

All identities, rules, prices, source references, notes and verification records in these
examples are invented. These files make no claim about actual markets, sources or accounts.
They are never imported into the default research workspace.

| Scenario | Canonical record | Shared evidence | Model handoffs |
| --- | --- | --- | --- |
| Single contract | [JSON](single-contract/canonical.json) | [Markdown](single-contract/shared.md) | [GPT](single-contract/gpt.md), [Claude](single-contract/claude.md) |
| Related contracts with different cutoffs | [JSON](multiple-deadlines/canonical.json) | [Markdown](multiple-deadlines/shared.md) | [GPT](multiple-deadlines/gpt.md), [Claude](multiple-deadlines/claude.md) |
| Weekly multi-contract distribution | [JSON](weekly-distribution/canonical.json) | [Markdown](weekly-distribution/shared.md) | [GPT](weekly-distribution/gpt.md), [Claude](weekly-distribution/claude.md) |

The weekly example leaves one displayed price unavailable; no complementary price or
normalized distribution is invented. Each event includes all of its child contracts and
outcomes. Trading cutoffs, separately sourced measurement periods and resolution deadlines
are distinct. Each scenario includes sourced evidence, questions, catalysts, hypotheses and
separate model interpretations.

Rebuild with `.venv/bin/python scripts/research_examples.py` (or your installed Python).
The script uses temporary SQLite databases, a fixed UTC time, invented public-shaped
inputs and no network. Repeated generation produces the same bytes and snapshot hashes.
Each directory contains an export manifest with file checksums.
