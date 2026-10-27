"""Neutral GET-only JSON transport. No credentials or account imports."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"

JsonOpener = Callable[..., Any]


class HttpReadError(RuntimeError):
    pass


class InvalidJsonResponseError(HttpReadError):
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
            raise HttpReadError("HTTP client only permits GET requests")
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
            raise HttpReadError(f"HTTP {exc.code} while reading {url}") from exc
        except URLError as exc:
            raise HttpReadError(f"Unable to read {url}: {exc.reason}") from exc
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
