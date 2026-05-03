# Read-Only Account Connection Plan

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

## Implementation Steps

1. Add a `polymarket_account` collector with a small HTTP client that rejects all non-GET methods.
2. Add pure normalization functions for:
   - public Data API positions,
   - authenticated portfolio positions,
   - authenticated account balances,
   - authenticated open orders.
3. Write imported data to generated files first, for example:
   - `reports/generated/account_positions_raw.json`
   - `reports/generated/account_balances_raw.json`
   - `reports/generated/account_open_orders_raw.json`
4. Add an explicit promotion command that converts reviewed imports into:
   - `context/portfolio_current.yaml`
   - `context/open_orders.yaml`
   - `context/live_state.yaml` account snapshot
5. Keep the existing manual workflow as the default until imported data has been reviewed.

## Commands To Add

Suggested read-only commands:

```bash
python -m polymarket_desk.cli import-public-positions \
  --wallet-address 0x... \
  --output reports/generated/account_positions_raw.json

python -m polymarket_desk.cli import-account-snapshot \
  --output-dir reports/generated/account
```

Do not add commands named `place`, `create`, `cancel`, `modify`, `execute`, `wallet`, or
`private-key`.
