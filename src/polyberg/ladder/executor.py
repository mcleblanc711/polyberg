"""Execute a LadderPlan: per-action human confirm, API cancels, manual placements.

Cancels go over the wire (DELETE /order via MutatingClobClient). Placements are
never sent — the executor prints the pipe-delimited paste line and asks the
user to confirm they placed it manually in the Polymarket UI. Every ATTEMPTED
action is appended to an append-only jsonl log, including declines.

There is deliberately no --yes / bulk-approve path: one confirmation per action.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    InvalidJsonResponseError,
    ReadOnlyHttpClient,
)
from polyberg.collectors.polymarket_clob_auth import (
    CLOB_API_BASE_URL,
    ClobCredentials,
    build_level_2_headers,
)
from polyberg.collectors.polymarket_clob_balance import (
    COLLATERAL_ASSET_TYPE,
    _resolve_signature_type,
)
from polyberg.config import get_timezone
from polyberg.ladder.clob_cancel import (
    RESPONSE_EXCERPT_CHARS,
    ClobCancelError,
    MutatingClobClient,
    cancel_order,
)
from polyberg.ladder.diff import LadderPlan
from polyberg.ladder.render import _place_paste_line

PREFLIGHT_PATH = "/balance-allowance/update"


def append_order_log(log_path: Path, entry: dict[str, Any]) -> None:
    """Append one action record to the jsonl order log (append-only)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _log_entry(
    ts: datetime,
    action: str,
    market_id: str,
    outcome: str,
    side: str,
    price: float,
    shares: float,
    order_id: str | None,
    status: str,
    response_excerpt: str = "",
) -> dict[str, Any]:
    return {
        "ts": ts.isoformat(),
        "action": action,
        "market_id": market_id,
        "outcome": outcome,
        "side": side,
        "price": price,
        "shares": shares,
        "order_id": order_id,
        "status": status,
        "response_excerpt": response_excerpt[:RESPONSE_EXCERPT_CHARS],
    }


def record_manual_placement(
    log_path: Path,
    market_id: str,
    outcome: str,
    side: str,
    price: float,
    shares: float,
    now: datetime | None = None,
) -> None:
    """Append a ``manual_confirmed`` PLACE entry — used when the human marks a
    placement as done in the GUI (mirrors the executor's manual-placement walk)."""
    ts = now if now is not None else datetime.now(get_timezone())
    append_order_log(
        log_path,
        _log_entry(
            ts, "PLACE", market_id, outcome, side, price, shares, None, "manual_confirmed"
        ),
    )


def fire_preflight(
    creds: ClobCredentials,
    http: ReadOnlyHttpClient | None = None,
    signature_type: int | None = None,
    timestamp_seconds: Callable[[], int] | None = None,
    env: dict[str, str] | None = None,
) -> Any:
    """GET /balance-allowance/update — required after any position close
    before the CLOB accepts new orders. Idempotent; fired whenever the plan
    contains placements."""
    sig_type = _resolve_signature_type(signature_type, env=env)
    client = http or ReadOnlyHttpClient(CLOB_API_BASE_URL)
    headers = build_level_2_headers(
        creds,
        method="GET",
        request_path=PREFLIGHT_PATH,
        timestamp_seconds=timestamp_seconds,
    )
    try:
        return client.get_json(
            PREFLIGHT_PATH,
            params={
                "asset_type": COLLATERAL_ASSET_TYPE,
                "signature_type": sig_type,
            },
            headers=headers,
        )
    except InvalidJsonResponseError as exc:
        # The endpoint returns an empty/plain-text body on HTTP 200; that is
        # still a successful pre-flight.
        return exc.raw_text


def execute_plan(
    plan: LadderPlan,
    creds: ClobCredentials,
    log_path: Path,
    confirm: Callable[[str], str] = input,
    cancel_client: MutatingClobClient | None = None,
    preflight_http: ReadOnlyHttpClient | None = None,
    now: datetime | None = None,
    timestamp_seconds: Callable[[], int] | None = None,
    url_map: dict[str, str] | None = None,
) -> int:
    """Walk the plan with one y/n confirmation per action. Returns exit code.

    Cancels: y -> DELETE /order via the API; anything else -> declined, no HTTP.
    Placements: print the paste line, ask "placed manually? [y/n/skip]".
    Exit 1 if the pre-flight or any cancel hit an HTTP error, else 0.
    """
    if not plan.cancel and not plan.place:
        print("Nothing to execute: plan has no cancels or placements.")
        return 0

    failures = 0

    if plan.place:
        print(f"Pre-flight: GET {PREFLIGHT_PATH} ...")
        try:
            fire_preflight(creds, http=preflight_http, timestamp_seconds=timestamp_seconds)
            print("Pre-flight OK.")
        except AccountImportError as exc:
            failures += 1
            print(f"Pre-flight failed: {exc}", file=sys.stderr)

    for c in plan.cancel:
        ts = now if now is not None else datetime.now(get_timezone())
        prompt = (
            f"CANCEL {c.market_id} {c.outcome} {c.action} @ {c.price:.4f} "
            f"x {c.shares:.1f} order_id={c.order_id} ({c.reason}) — cancel via API? [y/n] "
        )
        answer = confirm(prompt).strip().lower()
        if answer == "y":
            try:
                response = cancel_order(
                    creds,
                    c.order_id,
                    http=cancel_client,
                    timestamp_seconds=timestamp_seconds,
                )
                status = "ok"
                excerpt = json.dumps(response)
                print(f"  cancelled {c.order_id}")
            except ClobCancelError as exc:
                failures += 1
                status = "http_error"
                excerpt = exc.excerpt or str(exc)
                print(f"  cancel failed for {c.order_id}: {exc}", file=sys.stderr)
        else:
            status = "declined"
            excerpt = ""
        append_order_log(
            log_path,
            _log_entry(
                ts, "CANCEL", c.market_id, c.outcome, c.action,
                c.price, c.shares, c.order_id, status, excerpt,
            ),
        )

    for p in plan.place:
        ts = now if now is not None else datetime.now(get_timezone())
        url = (url_map or {}).get(p.market_id)
        print(_place_paste_line(p, url))
        answer = confirm("  placed manually? [y/n/skip] ").strip().lower()
        if answer == "y":
            status = "manual_confirmed"
        elif answer in ("skip", "s"):
            status = "skipped"
        else:
            status = "declined"
        append_order_log(
            log_path,
            _log_entry(
                ts, "PLACE", p.market_id, p.outcome, p.action,
                p.price, p.shares, None, status,
            ),
        )

    return 1 if failures else 0
