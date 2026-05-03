# Polymarket Desk

Polymarket Desk is a local-first research repo for structured prediction-market analysis. It keeps
stable market rules, live trading context, portfolio state, open orders, prompts, schemas, and
generated model packets in separate files so LLM analysis can be repeated and validated.

The first pass is file-based only. It does not connect to live APIs, place trades, use MCP, run a
dashboard, scrape websites, or touch wallets/private keys.

## Design

- Ubuntu/Linux is the primary runtime target.
- Windows is supported for local editing and testing.
- All Python paths use `pathlib`.
- Generated timestamp formats should be Windows-safe, for example `2026-04-26_0900`.
- Model outputs are never trusted until validated against local JSON schemas.
- Twitter/X sentiment, if added later, must be labelled noisy, non-authoritative, and catalyst-only.
- Every final order recommendation requires human review.
- `POLYMARKET_DESK_TIMEZONE` overrides the default `America/Edmonton` timezone.
- `POLYMARKET_DESK_MAX_CONTEXT_AGE_HOURS` overrides the default 36-hour freshness warning.
- JSON Schema validation uses `jsonschema` with `rfc3339-validator`; Python post-checks also
  require timezone-aware `as_of` values.

## Install On Ubuntu

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
```

Editable install is preferred for local development so package-relative defaults resolve to this
repo's `context/`, `schemas/`, and generated-report folders.

## Install On Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
```

## Common Commands

Ubuntu/Linux convenience commands:

```bash
make install
make test
make lint
make packet
make clean
```

Plain Python equivalents that work in Bash and PowerShell:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests
python -m polymarket_desk.cli build-packet --output reports/generated/packet.md
python -m polymarket_desk.cli snapshot-markets --output data/snapshots/markets_YYYY-MM-DD_HHMM.json
python -m polymarket_desk.cli diff-snapshots --old data/snapshots/markets_OLD.json --new data/snapshots/markets_NEW.json
python -m polymarket_desk.cli build-trade-ticket --adjudicator-output reports/generated/adjudicator_output.json --output reports/generated/trade_ticket.md
```

Validate model JSON:

```bash
python -m polymarket_desk.cli validate-response reports/generated/claude_output.json
```

Validate adjudicator JSON:

```bash
python -m polymarket_desk.cli validate-adjudicator reports/generated/adjudicator_output.json
```

Build adjudicator input in Bash:

```bash
python -m polymarket_desk.cli build-adjudicator-input \
  --packet reports/generated/packet.md \
  --model-output-a reports/generated/claude_output.json \
  --model-output-b reports/generated/chatgpt_output.json \
  --output reports/generated/adjudicator_input.md
```

Build adjudicator input in PowerShell:

```powershell
python -m polymarket_desk.cli build-adjudicator-input `
  --packet reports/generated/packet.md `
  --model-output-a reports/generated/claude_output.json `
  --model-output-b reports/generated/chatgpt_output.json `
  --output reports/generated/adjudicator_input.md
```

Build packets from another context directory:

```bash
python -m polymarket_desk.cli build-packet \
  --context-dir context \
  --snapshot data/snapshots/markets_YYYY-MM-DD_HHMM.json \
  --output reports/generated/packet.md
```

## Context Files

- `context/stable_rules.md`: durable resolution-rule notes and rule-key explanations.
- `context/trading_principles.md`: standing trading discipline and risk rules.
- `context/recent_catalysts.md`: manually curated recent news, rumours, and missing info.
- `context/live_state.yaml`: current mode, constraints, watchlist, and account snapshot.
- `context/portfolio_current.yaml`: current cash, value, and positions.
- `context/open_orders.yaml`: manually tracked buy and sell limit orders.
- `context/market_registry.yaml`: stable market IDs, URLs, categories, oracle types, and rule keys.
  Optional fields include Gamma/CLOB identifiers, read-only data collection flags, and rule-risk
  labels such as pure data oracle, official statement required, official + media fallback,
  credible reporting primary, and UMA / subjective.

## Prompts And Schemas

- `prompts/claude_trader_prompt.md`: aggressive trade idea generator.
- `prompts/chatgpt_risk_prompt.md`: risk and resolution-rules critic.
- `prompts/adjudicator_prompt.md`: compares model outputs against the packet.
- `schemas/model_trade_response.schema.json`: validates model trade outputs.
- `schemas/adjudicator_output.schema.json`: validates final adjudicator outputs.
- `schemas/market_snapshot.schema.json`: validates read-only market snapshots.
- `schemas/twitter_sentiment_response.schema.json`: future Grok/Twitter interpretation schema only.
  It is catalyst-only, non-authoritative, and has no API or scraping integration.
- `docs/account_connection.md`: planned read-only account import design for portfolio, balances,
  and open orders.

The generated packet includes a local freshness audit. It compares `as_of` timestamps across live
state, portfolio, and open orders, and flags stale or mismatched local context. It does not verify
live markets, news, order books, or oracle data.

## Manual Workflow

A. Update local context files:
`live_state.yaml`, `portfolio_current.yaml`, `open_orders.yaml`, `market_registry.yaml`, and
`recent_catalysts.md`.

B. Optional: create/read a market snapshot:

```bash
python -m polymarket_desk.cli snapshot-markets --output data/snapshots/markets_YYYY-MM-DD_HHMM.json
```

C. Build packet:

```bash
python -m polymarket_desk.cli build-packet --snapshot data/snapshots/markets_YYYY-MM-DD_HHMM.json --output reports/generated/packet.md
```

D. Paste packet into Claude trader prompt and save JSON to
`reports/generated/claude_output.json`.

E. Paste packet into ChatGPT risk prompt and save JSON to
`reports/generated/chatgpt_output.json`.

F. Validate model outputs:

```bash
python -m polymarket_desk.cli validate-response reports/generated/claude_output.json
python -m polymarket_desk.cli validate-response reports/generated/chatgpt_output.json
```

G. Build adjudicator input:

```bash
python -m polymarket_desk.cli build-adjudicator-input \
  --packet reports/generated/packet.md \
  --model-output-a reports/generated/claude_output.json \
  --model-output-b reports/generated/chatgpt_output.json \
  --output reports/generated/adjudicator_input.md
```

H. Paste adjudicator input into the adjudicator model and save JSON to
`reports/generated/adjudicator_output.json`.

I. Validate adjudicator:

```bash
python -m polymarket_desk.cli validate-adjudicator reports/generated/adjudicator_output.json
```

J. Build human trade ticket:

```bash
python -m polymarket_desk.cli build-trade-ticket \
  --adjudicator-output reports/generated/adjudicator_output.json \
  --output reports/generated/trade_ticket.md
```

K. A human manually reviews and places/cancels orders on Polymarket if desired.

## Git Setup

If starting from an unpacked directory rather than a cloned repo:

```bash
git init
git add .
git commit -m "initial local-first polymarket desk"
```

## Scope Boundaries

Intentionally out of scope for now:

- Automated trading.
- Live API execution.
- MCP.
- Dashboard or Streamlit UI.
- Wallet private-key integration.
- Browser automation.
- Scraping.
- Treating Twitter/X sentiment as fact.

This repo is meant to prepare clean context and enforce structured outputs. It is not an execution
system.
