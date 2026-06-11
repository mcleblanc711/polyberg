"""Mutating CLOB client for order cancellation — DELETE /order ONLY.

This is the single place in polyberg allowed to sign a non-GET CLOB request.
It is a separate class from ``ReadOnlyHttpClient`` on purpose: the read-only
client's GET-only invariant stays untouched, and this client refuses any
method/path other than ``DELETE /order``.

Signature compatibility with py-clob-client: the reference client signs
``str(body).replace("'", '"')`` (a Python dict repr with quotes swapped) and
sends ``json.dumps(body)`` over the wire. For ``{"orderID": "<hex>"}`` those
two strings are byte-identical, so we build the body once with ``json.dumps``
and use it for both the signature and the request payload.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from polyberg.collectors.polymarket_clob_auth import (
    CLOB_API_BASE_URL,
    POLY_ADDRESS_HEADER,
    POLY_API_KEY_HEADER,
    POLY_PASSPHRASE_HEADER,
    POLY_SIGNATURE_HEADER,
    POLY_TIMESTAMP_HEADER,
    ClobCredentials,
    build_hmac_signature,
)

ORDER_PATH = "/order"
USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"
RESPONSE_EXCERPT_CHARS = 300


class ClobCancelError(Exception):
    """A cancel attempt failed (HTTP error, transport error, or misuse)."""

    def __init__(self, message: str, status_code: int | None = None, excerpt: str = "") -> None:
        self.status_code = status_code
        self.excerpt = excerpt[:RESPONSE_EXCERPT_CHARS]
        super().__init__(message)


def build_level_2_mutating_headers(
    creds: ClobCredentials,
    method: str,
    request_path: str,
    body: str | None = None,
    timestamp_seconds=None,
) -> dict[str, str]:
    """Return the five POLY_* headers for a non-GET L2-authenticated request.

    Mirrors ``build_level_2_headers`` but without the GET-only guard; uses
    ``build_hmac_signature`` directly so the sign string stays interchangeable
    with the reference client.
    """
    import time

    now_seconds = timestamp_seconds() if timestamp_seconds else int(time.time())
    signature = build_hmac_signature(
        creds.api_secret,
        now_seconds,
        method.upper(),
        request_path,
        body,
    )
    return {
        POLY_ADDRESS_HEADER: creds.address,
        POLY_SIGNATURE_HEADER: signature,
        POLY_TIMESTAMP_HEADER: str(now_seconds),
        POLY_API_KEY_HEADER: creds.api_key,
        POLY_PASSPHRASE_HEADER: creds.api_passphrase,
    }


class MutatingClobClient:
    """HTTP client that signs and sends exactly one kind of request: DELETE /order."""

    def __init__(
        self, base_url: str = CLOB_API_BASE_URL, opener=urlopen, timeout: float = 30
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.opener = opener
        self.timeout = timeout

    def delete_json(self, path: str, body: str, headers: dict[str, str]) -> Any:
        if path != ORDER_PATH:
            raise ClobCancelError(
                f"MutatingClobClient only permits DELETE {ORDER_PATH}, got {path!r}"
            )
        url = self.base_url + path
        merged_headers: dict[str, str] = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        merged_headers.update(headers)
        # Same case-preservation workaround as ReadOnlyHttpClient: urllib's
        # Request(headers=...) capitalizes names (POLY_ADDRESS -> Poly_address)
        # which the CLOB rejects, so set them on the underlying dict directly.
        request = Request(url, data=body.encode("utf-8"), method="DELETE")
        for header_name, header_value in merged_headers.items():
            request.headers[header_name] = header_value
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - excerpt is best-effort
                error_body = ""
            raise ClobCancelError(
                f"HTTP {exc.code} from DELETE {url}: {error_body[:RESPONSE_EXCERPT_CHARS]}",
                status_code=exc.code,
                excerpt=error_body,
            ) from exc
        except URLError as exc:
            raise ClobCancelError(f"Unable to reach {url}: {exc.reason}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ClobCancelError(f"Invalid JSON response from DELETE {url}") from exc


def cancel_order(
    creds: ClobCredentials,
    order_id: str,
    http: MutatingClobClient | None = None,
    timestamp_seconds=None,
) -> Any:
    """Cancel one open order via DELETE /order. Returns the parsed response.

    Raises :class:`ClobCancelError` on any HTTP/transport failure.
    """
    body = json.dumps({"orderID": order_id})
    headers = build_level_2_mutating_headers(
        creds,
        method="DELETE",
        request_path=ORDER_PATH,
        body=body,
        timestamp_seconds=timestamp_seconds,
    )
    client = http or MutatingClobClient()
    return client.delete_json(ORDER_PATH, body, headers)
