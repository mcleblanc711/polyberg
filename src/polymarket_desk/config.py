from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEZONE = "America/Edmonton"


def repo_path(*parts: str) -> Path:
    return PACKAGE_ROOT.joinpath(*parts)


def windows_safe_timestamp(
    dt: datetime | None = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> str:
    if dt is None:
        dt = datetime.now(ZoneInfo(timezone_name))
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(timezone_name))
    return dt.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d_%H%M")
