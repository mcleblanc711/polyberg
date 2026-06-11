"""Read-only Polymarket account data importers.

This module intentionally exposes only GET-based account reads. It does not
create, modify, cancel, preview, close, sign, or submit orders.
"""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from polyberg.config import get_timezone

PUBLIC_DATA_API_BASE_URL = "https://data-api.polymarket.com"
POLYMARKET_US_API_BASE_URL = "https://api.polymarket.us"
DEFAULT_USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"

JsonOpener = Callable[..., Any]


class AccountImportError(RuntimeError):
    pass


class InvalidJsonResponseError(AccountImportError):
    """HTTP request succeeded but the body is not JSON. Carries the raw text
    for endpoints that legitimately return empty/plain-text bodies."""

    def __init__(self, message: str, raw_text: str) -> None:
        super().__init__(message)
        self.raw_text = raw_text


class ReadOnlyHttpClient:
    def __init__(self, base_url: str, opener: JsonOpener = urlopen, timeout: float = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.opener = opener
        self.timeout = timeout

    def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return self.request_json("GET", path, params=params, headers=headers)

    def request_json(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if method.upper() != "GET":
            raise AccountImportError("Account import client only permits GET requests")
        url = self.build_url(path, params)
        merged_headers: dict[str, str] = {"User-Agent": DEFAULT_USER_AGENT}
        if headers:
            merged_headers.update(headers)
        # urllib's Request(headers=...) routes through add_header(), which
        # capitalizes every name (POLY_ADDRESS -> Poly_address). Servers that
        # check header names case-sensitively (notably Polymarket's CLOB)
        # reject those. Set headers directly on the underlying dict so the
        # caller's exact case is preserved on the wire.
        request = Request(url, method="GET")
        for header_name, header_value in merged_headers.items():
            request.headers[header_name] = header_value
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            raise AccountImportError(f"HTTP {exc.code} while reading {url}") from exc
        except URLError as exc:
            raise AccountImportError(f"Unable to read {url}: {exc.reason}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidJsonResponseError(
                f"Invalid JSON response from {url}",
                raw_text=raw.decode("utf-8", errors="replace"),
            ) from exc

    def build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        if not path.startswith("/"):
            path = "/" + path
        query = build_query(params or {})
        suffix = f"{path}?{query}" if query else path
        return self.base_url + suffix


class PublicDataAccountClient:
    def __init__(self, http: ReadOnlyHttpClient | None = None) -> None:
        self.http = http or ReadOnlyHttpClient(PUBLIC_DATA_API_BASE_URL)

    def fetch_positions(
        self,
        wallet_address: str,
        size_threshold: float = 1.0,
        limit: int = 500,
        offset: int = 0,
    ) -> Any:
        validate_wallet_address(wallet_address)
        return self.http.get_json(
            "/positions",
            params={
                "user": wallet_address,
                "sizeThreshold": size_threshold,
                "limit": limit,
                "offset": offset,
            },
        )


class PolymarketUSReadOnlyClient:
    def __init__(
        self,
        key_id: str,
        secret_key: str,
        http: ReadOnlyHttpClient | None = None,
        timestamp_ms: Callable[[], int] | None = None,
    ) -> None:
        if not key_id:
            raise AccountImportError("Missing Polymarket US API key id")
        if not secret_key:
            raise AccountImportError("Missing Polymarket US secret key")
        self.key_id = key_id
        self.secret_key = secret_key
        self.http = http or ReadOnlyHttpClient(POLYMARKET_US_API_BASE_URL)
        self.timestamp_ms = timestamp_ms or (lambda: int(time.time() * 1000))

    @classmethod
    def from_env(cls, http: ReadOnlyHttpClient | None = None) -> PolymarketUSReadOnlyClient:
        return cls(
            key_id=os.environ.get("POLYMARKET_US_API_KEY_ID", ""),
            secret_key=os.environ.get("POLYMARKET_US_SECRET_KEY", ""),
            http=http,
        )

    def fetch_positions(self, market: str | None = None, limit: int = 100) -> Any:
        params: dict[str, Any] = {"limit": limit}
        if market:
            params["market"] = market
        return self._authenticated_get("/v1/portfolio/positions", params=params)

    def fetch_balances(self) -> Any:
        return self._authenticated_get("/v1/account/balances")

    def fetch_open_orders(self, slugs: list[str] | None = None) -> Any:
        params: dict[str, Any] = {}
        if slugs:
            params["slugs"] = slugs
        return self._authenticated_get("/v1/orders/open", params=params)

    def _authenticated_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        signed_path = build_signed_path(path, params or {})
        return self.http.get_json(
            path,
            params=params,
            headers=self.auth_headers("GET", signed_path),
        )

    def auth_headers(self, method: str, path: str) -> dict[str, str]:
        if method.upper() != "GET":
            raise AccountImportError("Account import client only signs GET requests")
        timestamp = str(self.timestamp_ms())
        message = f"{timestamp}{method.upper()}{path}"
        return {
            "X-PM-Access-Key": self.key_id,
            "X-PM-Timestamp": timestamp,
            "X-PM-Signature": sign_ed25519_message(self.secret_key, message),
            "Content-Type": "application/json",
        }


def write_public_positions(
    wallet_address: str,
    output_path: Path,
    client: PublicDataAccountClient | None = None,
) -> Path:
    payload = (client or PublicDataAccountClient()).fetch_positions(wallet_address)
    return write_account_json(
        output_path,
        {
            "as_of": datetime.now(get_timezone()).isoformat(),
            "source": "polymarket_data_api_positions",
            "wallet_address": wallet_address,
            "payload": payload,
        },
    )


def write_authenticated_account_snapshot(
    output_dir: Path,
    client: PolymarketUSReadOnlyClient | None = None,
) -> list[Path]:
    account = client or PolymarketUSReadOnlyClient.from_env()
    as_of = datetime.now(get_timezone()).isoformat()
    outputs = {
        "positions_raw.json": {
            "as_of": as_of,
            "source": "polymarket_us_portfolio_positions",
            "payload": account.fetch_positions(),
        },
        "balances_raw.json": {
            "as_of": as_of,
            "source": "polymarket_us_account_balances",
            "payload": account.fetch_balances(),
        },
        "open_orders_raw.json": {
            "as_of": as_of,
            "source": "polymarket_us_open_orders",
            "payload": account.fetch_open_orders(),
        },
    }
    return [
        write_account_json(output_dir / filename, payload)
        for filename, payload in outputs.items()
    ]


def write_account_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_query(params: dict[str, Any]) -> str:
    normalized: list[tuple[str, Any]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, list):
            normalized.extend((key, item) for item in value)
        else:
            normalized.append((key, value))
    return urlencode(normalized)


def build_signed_path(path: str, params: dict[str, Any]) -> str:
    if not path.startswith("/"):
        path = "/" + path
    query = build_query(params)
    return f"{path}?{query}" if query else path


def validate_wallet_address(value: str) -> None:
    if len(value) != 42 or not value.startswith("0x"):
        raise AccountImportError("Wallet address must be a 42-character 0x-prefixed address")
    if not all(char in "0123456789abcdefABCDEF" for char in value[2:]):
        raise AccountImportError("Wallet address must contain only hexadecimal characters")


def sign_ed25519_message(secret_key: str, message: str) -> str:
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:
        raise AccountImportError(
            "Install the 'cryptography' package to use authenticated Polymarket US imports"
        ) from exc

    try:
        private_key_bytes = base64.b64decode(secret_key)[:32]
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        return base64.b64encode(private_key.sign(message.encode("utf-8"))).decode("ascii")
    except ValueError as exc:
        raise AccountImportError("Invalid Polymarket US secret key") from exc
