from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEZONE = "America/Edmonton"
DEFAULT_MAX_CONTEXT_AGE_HOURS = 36


def repo_path(*parts: str) -> Path:
    return PACKAGE_ROOT.joinpath(*parts)


def get_timezone_name() -> str:
    return os.environ.get("POLYBERG_TIMEZONE", DEFAULT_TIMEZONE)


def get_timezone(timezone_name: str | None = None) -> ZoneInfo:
    name = timezone_name or get_timezone_name()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Invalid timezone {name!r}. Set POLYBERG_TIMEZONE to a valid IANA "
            "timezone such as 'America/Edmonton' or 'UTC'."
        ) from exc


def get_max_context_age_hours() -> float:
    raw = os.environ.get("POLYBERG_MAX_CONTEXT_AGE_HOURS")
    if raw is None:
        return DEFAULT_MAX_CONTEXT_AGE_HOURS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            "Invalid POLYBERG_MAX_CONTEXT_AGE_HOURS. Set it to a positive number."
        ) from exc
    if value <= 0:
        raise ValueError(
            "Invalid POLYBERG_MAX_CONTEXT_AGE_HOURS. Set it to a positive number."
        )
    return value


def windows_safe_timestamp(
    dt: datetime | None = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> str:
    tz = get_timezone(timezone_name)
    if dt is None:
        dt = datetime.now(tz)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz).strftime("%Y-%m-%d_%H%M")
