# Polyberg

A local-first research workbench for structured prediction-market analysis on
Polymarket. Polyberg keeps stable market rules, live trading context, portfolio
state, open orders, prompts, schemas, and generated model packets in separate
versioned files so LLM-driven analysis can be repeated, validated, and
human-reviewed before any trade is placed.

It ships as a Python CLI plus an Electron desktop GUI that wraps the same
stages. Both are **strictly read-only** against Polymarket: no order placement,
no wallet private keys, no browser automation.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Ubuntu%20%7C%20Windows-lightgrey.svg)

---

## Screens

**Dashboard** — positions, freshness audit, research workflow, account rail.

![Dashboard](design/screenshots/01-dashboard.png)

**Intake / context rebuilder** — paste tweets, articles, notes; auto-tag to
markets; diff before any file is written.

![Intake](design/screenshots/02-intake.png)

**Snapshots** — structured market-snapshot scaffold with diff against prior
captures. The live Gamma/CLOB collector wiring is a known gap; the current
`snapshot-markets` command emits the schema with placeholder prices.

![Snapshots](design/screenshots/03-snapshots.png)

**Catalysts** — manually curated `recent_catalysts.md` viewer with attribution.

![Catalysts](design/screenshots/04-catalysts.png)

**Packet review** — generated `packet.md` next to adjudicator status and next
stage.

![Packet](design/screenshots/05-packet.png)

**Markets** — registry view with rule keys, oracle types, and resolution risk
flags.

![Markets](design/screenshots/06-markets.png)

---

## What Polyberg does

1. Gathers local context (rules, principles, catalysts, watchlist, portfolio,
   open orders, market registry).
2. Optionally pulls **read-only** snapshots from Polymarket public/Gamma APIs
   and an authenticated CLOB GET path for balances and open orders.
3. Builds a deterministic `packet.md` you paste into an LLM trader prompt and a
   separate risk/rules prompt.
4. Validates each model's JSON output against local schemas.
5. Builds an adjudicator input, validates the adjudicator's verdict.
6. Renders a human-readable trade ticket.
7. A human reviews and places orders on Polymarket manually. Polyberg never
   does.

The generated packet includes a freshness audit that compares `as_of`
timestamps across local context and flags stale or mismatched data. It does
not verify live markets, news, order books, or oracle data.

## Safety boundary

| Capability                | Status               |
|---------------------------|----------------------|
| Read Polymarket public API| ✅ supported         |
| Read CLOB balances/orders | ✅ via L2 HMAC (GET) |
| Place / cancel orders     | ❌ never             |
| Hold wallet private keys  | ❌ never             |
| Auto-execute model output | ❌ never             |
| Browser automation        | ❌ never             |
| Scrape websites           | ❌ never             |

Authenticated reads use a pre-minted `(api_key, secret, passphrase)` triple
plus the signer EOA address for the Polymarket CLOB. An optional Polymarket
US API key/secret pair is also supported for tenants that use that API
surface; both paths are GET-only. The repo never touches your wallet's
private key. See [`docs/account_connection.md`](docs/account_connection.md)
for the full credential model.

---

## Install — Ubuntu / Linux (primary target)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
```

Editable install is preferred so package-relative defaults resolve to this
repo's `context/`, `schemas/`, and `reports/generated/` folders.

## Install — Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
```

## Configure local secrets

Copy `.env.example` to `.env` and fill in only the credentials you want to
use. All fields are optional — Polyberg degrades gracefully when a credential
is missing.

```bash
cp .env.example .env
```

The CLI auto-loads `.env` from the repo root on every invocation, including
stages spawned by the Electron GUI. Real shell-env values always win over
`.env`.

## Local-only overlays

Identifying data (real wallet, real portfolio, real order ladder) should never
be committed. The tracked files in `context/` ship with **sample data**. Drop
your real data into gitignored sibling files:

| Sample (tracked)              | Real data (gitignored)              |
|-------------------------------|-------------------------------------|
| `context/live_state.yaml`     | `context/live_state.local.yaml`     |
| `context/portfolio_current.yaml` | `context/portfolio_current.local.yaml` |
| `context/open_orders.yaml`    | `context/open_orders.local.yaml`    |

The GUI reads `live_state.local.yaml` as an overlay on top of
`live_state.yaml` (so the real proxy wallet stays out of the tracked file).
The Python CLI does **not** apply overlays today — it reads only the tracked
context files. For `portfolio_current`, `open_orders`, and
`recent_catalysts.md`, treat the `.local.*` siblings as your private reference
copy and either restore the real content into the tracked files locally and
use `git update-index --skip-worktree` to keep git quiet, or import via the
GUI / CLI which writes the tracked files directly.

---

## GUI

The Electron desktop GUI wraps every CLI stage and adds an intake/diff editor
for `recent_catalysts.md`, paste-import flows for portfolio JSON, and live
freshness indicators.

```bash
cd gui
npm install
npm run dev
```

Build a distributable:

```bash
cd gui
npm run build
```

## CLI workflow

### Convenience targets (Ubuntu/Linux)

```bash
make install
make test
make lint
make packet
make clean
```

### Plain Python (works on Bash and PowerShell)

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests
```

### Manual stage-by-stage

A. Update local context: `live_state.yaml`, `portfolio_current.yaml`,
`open_orders.yaml`, `market_registry.yaml`, `recent_catalysts.md`.

B. Optional — create a market snapshot:

```bash
python -m polyberg.cli snapshot-markets \
  --output data/snapshots/markets_YYYY-MM-DD_HHMM.json
```

C. Optional — import read-only account data:

```bash
python -m polyberg.cli import-public-positions \
  --address 0x... \
  --output reports/generated/account_positions_raw.json

python -m polyberg.cli import-account-snapshot \
  --output-dir reports/generated/account

python -m polyberg.cli import-clob-orders \
  --output reports/generated/account/open_orders_raw.json

python -m polyberg.cli import-clob-balance \
  --output reports/generated/account/balance.json
```

D. Build packet:

```bash
python -m polyberg.cli build-packet \
  --snapshot data/snapshots/markets_YYYY-MM-DD_HHMM.json \
  --output reports/generated/packet.md
```

E. Paste packet into the Claude trader prompt; save JSON to
`reports/generated/claude_output.json`.

F. Paste packet into the ChatGPT risk prompt; save JSON to
`reports/generated/chatgpt_output.json`.

G. Validate model outputs:

```bash
python -m polyberg.cli validate-response reports/generated/claude_output.json
python -m polyberg.cli validate-response reports/generated/chatgpt_output.json
```

H. Build adjudicator input:

```bash
python -m polyberg.cli build-adjudicator-input \
  --packet reports/generated/packet.md \
  --model-output-a reports/generated/claude_output.json \
  --model-output-b reports/generated/chatgpt_output.json \
  --output reports/generated/adjudicator_input.md
```

I. Paste adjudicator input into the adjudicator model; save JSON to
`reports/generated/adjudicator_output.json`.

J. Validate adjudicator:

```bash
python -m polyberg.cli validate-adjudicator reports/generated/adjudicator_output.json
```

K. Build human trade ticket:

```bash
python -m polyberg.cli build-trade-ticket \
  --adjudicator-output reports/generated/adjudicator_output.json \
  --output reports/generated/trade_ticket.md
```

L. A human reviews the trade ticket and places or cancels orders on
Polymarket manually.

---

## Repository layout

```
context/        # editable inputs: rules, principles, catalysts, registry, state
prompts/        # LLM prompt templates
schemas/        # JSON schemas for model + adjudicator + snapshot outputs
src/polyberg/   # Python CLI + collectors + builders + validators
gui/            # Electron desktop GUI (TypeScript / React)
docs/           # design and account-connection docs
data/snapshots/ # generated read-only market snapshots (gitignored)
reports/        # generated packets, adjudicator I/O, trade tickets (gitignored)
tests/          # pytest suite
```

## Design notes

- Ubuntu/Linux is the primary runtime target; Windows is supported for local
  editing and testing.
- All Python paths use `pathlib`.
- Generated timestamps are Windows-safe (e.g., `2026-04-26_0900`).
- Model outputs are never trusted until validated against local JSON schemas.
- Twitter/X sentiment, if added later, is labelled noisy, non-authoritative,
  and catalyst-only.
- Every final order recommendation requires human review.
- `POLYBERG_TIMEZONE` overrides the default `America/Edmonton`.
- `POLYBERG_MAX_CONTEXT_AGE_HOURS` overrides the default 36-hour freshness
  warning.
- JSON Schema validation uses `jsonschema` with `rfc3339-validator`; Python
  post-checks also require timezone-aware `as_of` values.

## Context files

- `context/stable_rules.md` — durable resolution-rule notes and rule-key
  explanations.
- `context/trading_principles.md` — standing trading discipline and risk rules.
- `context/recent_catalysts.md` — manually curated recent news, rumours, and
  missing info.
- `context/live_state.yaml` — current mode, constraints, watchlist, and
  account snapshot.
- `context/portfolio_current.yaml` — current cash, value, and positions.
- `context/open_orders.yaml` — manually tracked buy and sell limit orders.
- `context/market_registry.yaml` — stable market IDs, URLs, categories, oracle
  types, and rule keys. Optional fields include Gamma/CLOB identifiers,
  read-only data collection flags, and rule-risk labels.

## Prompts and schemas

- `prompts/claude_trader_prompt.md` — aggressive trade idea generator.
- `prompts/chatgpt_risk_prompt.md` — risk and resolution-rules critic.
- `prompts/adjudicator_prompt.md` — compares model outputs against the packet.
- `schemas/model_trade_response.schema.json` — validates model trade outputs.
- `schemas/adjudicator_output.schema.json` — validates final adjudicator
  outputs.
- `schemas/market_snapshot.schema.json` — validates read-only market snapshots.
- `schemas/twitter_sentiment_response.schema.json` — future Grok/Twitter
  interpretation schema only. Catalyst-only, non-authoritative, no API or
  scraping integration today.

## Scope boundaries

Intentionally out of scope:

- Automated trading.
- Live order placement.
- MCP integration.
- Wallet private-key handling.
- Browser automation.
- Site scraping.
- Treating Twitter/X sentiment as fact.

Polyberg prepares clean context and enforces structured outputs. It is not an
execution system.

## License

MIT — see [LICENSE](LICENSE).
