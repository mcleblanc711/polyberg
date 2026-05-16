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


def load_repo_dotenv(path: Path | None = None) -> int:
    """Populate ``os.environ`` from the repo-root ``.env`` file.

    Hand-rolled to avoid a python-dotenv dependency. Only sets keys that are
    not already present, so a real shell env still wins. Lines starting with
    ``#`` and blank lines are ignored; values may be wrapped in matching
    single or double quotes which are stripped. Returns the number of keys
    populated. Missing or unreadable ``.env`` is a no-op (returns 0) — this
    keeps the CLI usable without any .env on systems that pass creds via
    other means (CI, systemd, etc.).
    """
    env_path = path or repo_path(".env")
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    written = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value
        written += 1
    return written


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
