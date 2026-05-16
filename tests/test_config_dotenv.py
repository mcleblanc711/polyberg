from __future__ import annotations

import os
from pathlib import Path

import pytest

from polyberg.config import load_repo_dotenv


@pytest.fixture(autouse=True)
def _clear_marker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("DOTENV_TEST_KEY", "DOTENV_TEST_KEEP", "DOTENV_QUOTED"):
        monkeypatch.delenv(key, raising=False)


def test_load_repo_dotenv_populates_missing_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# comment\n\nDOTENV_TEST_KEY=hello\nDOTENV_QUOTED=\"a b\"\n",
        encoding="utf-8",
    )
    written = load_repo_dotenv(env_path)
    assert written == 2
    assert os.environ["DOTENV_TEST_KEY"] == "hello"
    assert os.environ["DOTENV_QUOTED"] == "a b"


def test_load_repo_dotenv_does_not_override_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOTENV_TEST_KEEP", "from_shell")
    env_path = tmp_path / ".env"
    env_path.write_text("DOTENV_TEST_KEEP=from_file\n", encoding="utf-8")
    written = load_repo_dotenv(env_path)
    assert written == 0
    assert os.environ["DOTENV_TEST_KEEP"] == "from_shell"


def test_load_repo_dotenv_missing_file_is_noop(tmp_path: Path) -> None:
    assert load_repo_dotenv(tmp_path / "absent.env") == 0
