# Read-Only Account Connection

Goal: import portfolio, balances, and open orders into local context files. The
import/normalize stack adds no trade-execution surface; the only write path in the
whole repo is the ladder manager's order **cancellation** (DELETE /order), which is
isolated, opt-in, and human-confirmed per action — see
[Ladder reconciliation (the one write path)](#ladder-reconciliation-the-one-write-path).

## Safety Boundary

- No wallet private keys, ever.
- No order **creation** (`place`), modification, close-position, bridge, deposit, or
  withdrawal calls. Placements are surfaced as copy-paste lines for the human to enter
  in the Polymarket UI; polyberg never sends them.
- Order **cancellation** is the single deliberate exception (DELETE /order), confined to
  `ladder/clob_cancel.py`'s `MutatingClobClient` and gated behind per-action human
  confirmation. Everything else stays read-only.
- No browser automation.
- The import/normalize stack (`ReadOnlyHttpClient`) allows only `GET` requests; its
  GET-only invariant is untouched by the cancel path, which uses a separate client class.
- Imported account data remains advisory context and is still validated before packet generation.

## Data Sources

### Public positions by address

Use the public Polymarket Data API for current positions when a proxy-wallet address is available.

- Base: `https://data-api.polymarket.com`
- Endpoint: `GET /positions`
- Key input: `user=<wallet_or_proxy_wallet_address>`
- Useful filters: `sizeThreshold`, `limit`, `offset`, `market`

This path does not provide open orders or account balances, but it avoids API credentials.

### USDC balance via CLOB `/balance-allowance`

Polyberg used to fetch the proxy wallet's idle USDC.e balance via a direct on-chain
`eth_call` against Polygon. That path has been replaced: the CLOB exposes a
`/balance-allowance` endpoint (authenticated via the same L2 HMAC scheme as open
orders) that returns the wallet's collateral with `signature_type=1` for proxy-wallet
accounts. See `collectors/polymarket_clob_balance.py`.

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
# Positions via public Data API (unauth)
python -m polyberg.cli import-public-positions --address 0x...

# Open orders via CLOB L2 auth
python -m polyberg.cli import-clob-orders

# USDC collateral balance via CLOB L2 auth
python -m polyberg.cli import-clob-balance

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

## Ladder reconciliation (the one write path)

The ladder manager (`src/polyberg/ladder/`) reconciles a declared target order book
(`live/target_ladders.yaml`, with a gitignored `live/target_ladders.local.yaml` overlay)
against live CLOB open orders and emits a human-reviewable plan: which orders to cancel,
which to place, which to keep. It is the only part of polyberg that mutates account state,
and it does so for **cancels only**.

- **Cancels** go over the wire via `ladder/clob_cancel.py` → `MutatingClobClient`, which
  signs and sends exactly one kind of request: `DELETE /order` with body `{"orderID": ...}`.
  The body is built once with `json.dumps` and reused for both the HMAC signature and the
  payload so it stays byte-identical to py-clob-client's reference signing. Non-GET L2
  headers come from `build_level_2_mutating_headers` (the read-only stack's GET-only
  `build_level_2_headers` guard is left alone).
- **Placements** are never sent. The executor prints the pipe-delimited paste line and asks
  the human to confirm they placed it by hand; the action is logged as `manual_confirmed`.
- Every attempted action (including declines) is appended to the gitignored append-only
  log `live/order_log.jsonl`.

### Pre-flight rule

After any position is closed, the CLOB will reject new orders until the account's
collateral allowance is refreshed. So **whenever a plan contains placements**, the plan
prepends a pre-flight step: `GET /balance-allowance/update`. This is a cheap, idempotent
GET (it works through the read-only stack); it is fired unconditionally when placing
because closes can't be reliably detected. `ladder execute` fires it before the first
action; the GUI exposes it as a "RUN PRE-FLIGHT" button.

### Surfaces

```bash
# Diff target ladders vs live book; print a markdown reconciliation plan (+ paste block)
python -m polyberg.cli ladder plan

# Same, but emit machine-readable JSON (used by the GUI LADDER tab)
python -m polyberg.cli ladder plan --json

# Build a fresh plan, then walk it with per-action y/n confirmation
#   (cancels via API; placements as manual paste lines)
python -m polyberg.cli ladder execute

# GUI-support one-shot subcommands (the GUI confirm modal is the human gate):
python -m polyberg.cli ladder cancel --order-id <id>          # single API cancel + log
python -m polyberg.cli ladder preflight                       # fire GET /balance-allowance/update
python -m polyberg.cli ladder record-manual --market <id> \
    --outcome YES|NO --side BUY|SELL --price <p> --shares <n>  # log a manual placement
```

The GUI **LADDER** tab (`gui/src/renderer/src/screens/ladder/LadderScreen.tsx`) renders
the JSON plan as grouped CANCEL / PLACE / KEEP / UNMANAGED sections. Each cancel and each
manual placement requires its own confirm modal — there is deliberately no bulk-approve
control anywhere, mirroring the CLI's no-`--yes` design.

`signature_type` for these requests is env-driven via `POLYMARKET_CLOB_SIGNATURE_TYPE`
(default `1`, verified working for this proxy-wallet account).

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

Do not add commands named `place`, `create`, `modify`, `wallet`, or `private-key`, and do
not add any write path beyond the one documented above. Order cancellation already exists
as the single deliberate exception (`ladder cancel` / `ladder execute`, DELETE /order only);
do not broaden it to order placement or any other mutating endpoint.
