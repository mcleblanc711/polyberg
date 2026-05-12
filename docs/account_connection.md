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

### USDC balance via Polygon RPC

The proxy wallet's idle USDC.e balance is fetched by direct on-chain `eth_call` to the
USDC.e ERC-20 contract on Polygon. Default RPC is `https://polygon.drpc.org`; override with
the `POLYGON_RPC_URL` env var.

- Contract: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` (USDC.e, 6 decimals)
- Method: `balanceOf(address)` via JSON-RPC `eth_call`

This is unauthenticated, GET-only at the HTTP layer (a POST is required by JSON-RPC but the
intent is read-only). No private key, no signing.

### Open orders via CLOB L2 auth

The Polymarket CLOB exposes per-wallet open orders behind an HMAC L2 scheme. Polyberg uses
pre-minted credentials so the running process never holds a private key.

- Base: `https://clob.polymarket.com`
- Endpoint: `GET /data/orders`
- Headers: `POLY_ADDRESS`, `POLY_SIGNATURE`, `POLY_TIMESTAMP`, `POLY_API_KEY`, `POLY_PASSPHRASE`
- Sign string: `f"{unix_seconds}{METHOD}{request_path}{body?}"` over base64url-decoded secret;
  HMAC-SHA256; signature is base64url-encoded.

Required env vars:

- `POLYMARKET_CLOB_SIGNER_ADDRESS` — the **EOA address** (the externally-owned
  account derived from the private key that minted these creds). The CLOB
  registers each api_key against its signer EOA and rejects requests whose
  `POLY_ADDRESS` header doesn't match.
- `POLYMARKET_CLOB_API_KEY`
- `POLYMARKET_CLOB_SECRET`
- `POLYMARKET_CLOB_PASSPHRASE`

Note: the signer EOA is **not** the same as `POLYMARKET_PROXY_WALLET`. The
proxy wallet is the Polymarket-deployed contract that holds funds; the EOA
is what signs on its behalf. For email/social-login accounts (Gnosis-Safe-
style proxies), the EOA is whatever address the embedded wallet manages
under the hood — it shows up in the output of py-clob-client's
`get_address()` method or in any EIP-712-aware tool that derives an address
from the private key.

To mint these, run the official `py-clob-client`'s `create_or_derive_api_creds` once on a
trusted machine with your private key (or use the Polymarket web UI's developer settings),
then paste the four values into `.env`. After that, polyberg only uses the L2 triple — the
private key never enters this repo. The CLOB credentials are read-only in polyberg (only GET
`/data/orders` is reachable through `import-clob-orders`); they cannot be used to place or
cancel orders from inside this codebase.

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
# Positions + on-chain USDC balance (unauth)
python -m polyberg.cli import-public-positions --address 0x...

# Open orders via CLOB L2 auth
python -m polyberg.cli import-clob-orders

# Authenticated PM-US snapshot (positions, balances, open orders)
python -m polyberg.cli import-account-snapshot

# Normalize raw imports into canonical context (each is dry-run-able with --dry-run)
python -m polyberg.cli promote-positions
python -m polyberg.cli promote-orders
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
