# Read-Only Account Connection

Goal: import portfolio, balances, and open orders into local context files without adding any
trade-execution surface.

## Safety Boundary

- No wallet private keys.
- No order creation, modification, cancellation, close-position, bridge, deposit, or withdrawal calls.
- No browser automation.
- Authenticated code must allow only `GET` requests.
- Imported account data remains advisory context and is still validated before packet generation.

## Data Sources

### Public positions by address

Use the public Polymarket Data API for current positions when a proxy-wallet address is available.

- Base: `https://data-api.polymarket.com`
- Endpoint: `GET /positions`
- Key input: `user=<wallet_or_proxy_wallet_address>`
- Useful filters: `sizeThreshold`, `limit`, `offset`, `market`

This path does not provide open orders or account balances, but it avoids API credentials.

### Authenticated Polymarket US account data

Use the authenticated Polymarket US API only for read-only account endpoints.

- Base: `https://api.polymarket.us`
- Positions: `GET /v1/portfolio/positions`
- Balances: `GET /v1/account/balances`
- Open orders: `GET /v1/orders/open`

The API requires `X-PM-Access-Key`, `X-PM-Timestamp`, and `X-PM-Signature` headers. The signing key
should be read from environment variables at runtime and never written into reports or context files.

## Current Implementation

Implemented commands:

```bash
python -m polyberg.cli import-public-positions \
  --address 0x... \
  --output reports/generated/account_positions_raw.json

python -m polyberg.cli import-account-snapshot \
  --output-dir reports/generated/account
```

`import-public-positions` writes raw public Data API positions for a wallet/proxy-wallet address.

`import-account-snapshot` writes:

- `positions_raw.json`
- `balances_raw.json`
- `open_orders_raw.json`

It reads `POLYMARKET_US_API_KEY_ID` and `POLYMARKET_US_SECRET_KEY` from the environment and signs
only GET requests.

## Remaining Implementation Steps

1. Add pure normalization functions for:
   - public Data API positions,
   - authenticated portfolio positions,
   - authenticated account balances,
   - authenticated open orders.
2. Add an explicit promotion command that converts reviewed imports into:
   - `context/portfolio_current.yaml`
   - `context/open_orders.yaml`
   - `context/live_state.yaml` account snapshot
3. Keep the existing manual workflow as the default until imported data has been reviewed.

Do not add commands named `place`, `create`, `cancel`, `modify`, `execute`, `wallet`, or
`private-key`.
