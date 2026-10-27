"""Numbered, transactional SQLite migrations and research-only persistence."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from polyberg.config import repo_path
from polyberg.research.models import canonical, utcnow

MIGRATIONS = [
    (
        1,
        """
CREATE TABLE events (
 event_id TEXT PRIMARY KEY, data TEXT NOT NULL
);
CREATE TABLE markets (
 market_id TEXT PRIMARY KEY, event_id TEXT, identification TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'discovered'
 CHECK(status IN ('discovered','screening','researching','monitoring','rejected','archived')),
 previous_status TEXT, followed INTEGER NOT NULL DEFAULT 0 CHECK(followed IN (0,1)),
 last_attempt_at TEXT, last_success_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX markets_event ON markets(event_id);
CREATE TABLE outcomes (
 outcome_id TEXT PRIMARY KEY, market_id TEXT NOT NULL REFERENCES markets(market_id),
 ordinal INTEGER NOT NULL, label TEXT NOT NULL, token_id TEXT, position_id TEXT, asset_id TEXT,
 UNIQUE(market_id, ordinal)
);
CREATE TABLE refresh_attempts (
 attempt_id INTEGER PRIMARY KEY, market_id TEXT REFERENCES markets(market_id),
 reference TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('success','partial','failed')), message TEXT
);
CREATE TABLE rules_versions (
 rules_version_id INTEGER PRIMARY KEY, market_id TEXT NOT NULL REFERENCES markets(market_id),
 content_hash TEXT NOT NULL, data TEXT NOT NULL, first_retrieved_at TEXT NOT NULL,
 UNIQUE(market_id, content_hash)
);
CREATE TABLE rules_observations (
 observation_id INTEGER PRIMARY KEY, market_id TEXT NOT NULL REFERENCES markets(market_id),
 rules_version_id INTEGER REFERENCES rules_versions(rules_version_id), retrieved_at TEXT NOT NULL
);
CREATE TABLE rules_annotations (
 annotation_id INTEGER PRIMARY KEY,
 rules_version_id INTEGER NOT NULL REFERENCES rules_versions(rules_version_id),
 kind TEXT NOT NULL, text TEXT NOT NULL, source_url TEXT NOT NULL, created_at TEXT NOT NULL,
 needs_review INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE market_snapshots (
 snapshot_id INTEGER PRIMARY KEY, market_id TEXT NOT NULL REFERENCES markets(market_id),
 attempt_id INTEGER NOT NULL REFERENCES refresh_attempts(attempt_id),
 rules_version_id INTEGER REFERENCES rules_versions(rules_version_id),
 retrieved_at TEXT NOT NULL, identification TEXT NOT NULL, warnings TEXT NOT NULL
);
CREATE TABLE outcome_quotes (
 snapshot_id INTEGER NOT NULL REFERENCES market_snapshots(snapshot_id),
 outcome_id TEXT NOT NULL REFERENCES outcomes(outcome_id), data TEXT NOT NULL,
 PRIMARY KEY(snapshot_id, outcome_id)
);
CREATE TABLE projects (
 project_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);
CREATE TABLE project_markets (
 project_id INTEGER NOT NULL REFERENCES projects(project_id),
 market_id TEXT NOT NULL REFERENCES markets(market_id),
 PRIMARY KEY(project_id,market_id)
);
CREATE TABLE tags (
 market_id TEXT NOT NULL REFERENCES markets(market_id), tag TEXT NOT NULL,
 PRIMARY KEY(market_id,tag)
);
CREATE TABLE research_entries (
 entry_id INTEGER PRIMARY KEY, market_id TEXT NOT NULL REFERENCES markets(market_id),
 category TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL, verified_at TEXT
);
CREATE TABLE sources (
 source_id INTEGER PRIMARY KEY, content_hash TEXT NOT NULL UNIQUE, data TEXT NOT NULL
);
CREATE TABLE entry_sources (
 entry_id INTEGER NOT NULL REFERENCES research_entries(entry_id),
 source_id INTEGER NOT NULL REFERENCES sources(source_id), PRIMARY KEY(entry_id,source_id)
);
CREATE TABLE relationships (
 relationship_id INTEGER PRIMARY KEY,
 from_market TEXT NOT NULL REFERENCES markets(market_id),
 to_market TEXT NOT NULL REFERENCES markets(market_id), kind TEXT NOT NULL,
 explanation TEXT NOT NULL, source_url TEXT, created_at TEXT NOT NULL,
 CHECK(from_market != to_market), UNIQUE(from_market,to_market,kind)
);
CREATE TABLE workspace_history (
 history_id INTEGER PRIMARY KEY, market_id TEXT NOT NULL REFERENCES markets(market_id),
 action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE packet_snapshots (
 packet_id TEXT PRIMARY KEY, snapshot_sha256 TEXT NOT NULL, data TEXT NOT NULL,
 generated_at TEXT NOT NULL
);
CREATE TABLE exports (
 export_id INTEGER PRIMARY KEY, packet_id TEXT NOT NULL REFERENCES packet_snapshots(packet_id),
 directory TEXT NOT NULL, manifest TEXT NOT NULL, created_at TEXT NOT NULL
);
""",
    )
]

# Append-only provenance is enforced by SQLite as well as by the Python API.
_IMMUTABLE = (
    "refresh_attempts",
    "market_snapshots",
    "outcome_quotes",
    "rules_versions",
    "rules_observations",
    "sources",
    "packet_snapshots",
    "workspace_history",
    "exports",
)


def _immutable(tables: tuple[str, ...]) -> str:
    return "\n".join(
        f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'Immutable research record'); END;"
        for table in tables
        for action in ("UPDATE", "DELETE")
    )


MIGRATIONS[0] = (1, MIGRATIONS[0][1] + _immutable(_IMMUTABLE))
# Activity is append-only provenance like snapshots. Price history is a prunable cache:
# each (outcome, span) keeps only its latest successful retrieval.
MIGRATIONS.append(
    (
        2,
        """
CREATE TABLE market_activity (
 snapshot_id INTEGER PRIMARY KEY REFERENCES market_snapshots(snapshot_id),
 market_id TEXT NOT NULL REFERENCES markets(market_id), data TEXT NOT NULL
);
CREATE INDEX market_activity_market ON market_activity(market_id, snapshot_id);
CREATE TABLE price_history_fetches (
 fetch_id INTEGER PRIMARY KEY, outcome_id TEXT NOT NULL REFERENCES outcomes(outcome_id),
 span TEXT NOT NULL CHECK(span IN ('1d','1w','1m','max')),
 source_url TEXT NOT NULL, retrieved_at TEXT NOT NULL, points TEXT NOT NULL,
 warnings TEXT NOT NULL
);
CREATE INDEX price_history_latest ON price_history_fetches(outcome_id, span, fetch_id);
"""
        + _immutable(("market_activity",)),
    )
)


def _statements(script: str):
    statement = ""
    for character in script:
        statement += character
        if character == ";" and sqlite3.complete_statement(statement):
            yield statement
            statement = ""
    if statement.strip():
        raise ValueError("Incomplete research migration statement")


def database_path(path: Path | str | None = None) -> Path:
    return (
        Path(
            path
            or os.environ.get("POLYBERG_RESEARCH_DB")
            or repo_path("data", "research", "research.sqlite3")
        )
        .expanduser()
        .resolve()
    )


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = database_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA busy_timeout = 5000")
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version > MIGRATIONS[-1][0]:
                raise ValueError("Research database schema is newer than this application")
            if version == MIGRATIONS[-1][0]:
                return  # Read-only opens do not touch storage or trigger watchers.
            with self.transaction():
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                if version > MIGRATIONS[-1][0]:
                    raise ValueError("Research database schema is newer than this application")
                for number, script in MIGRATIONS:
                    if number > version:
                        # executescript commits implicitly; execute each statement inside BEGIN.
                        for statement in _statements(script):
                            self.db.execute(statement)
                        self.db.execute(f"PRAGMA user_version = {number}")
                self.db.execute(
                    "INSERT OR IGNORE INTO projects(name,created_at) VALUES ('default',?)",
                    (utcnow(),),
                )
        except BaseException:
            self.close()
            raise

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def one(self, sql: str, params: tuple = ()) -> dict | None:
        row = self.db.execute(sql, params).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(row) for row in self.db.execute(sql, params).fetchall()]

    def history(self, market_id: str, action: str, detail: str) -> None:
        self.db.execute(
            "INSERT INTO workspace_history(market_id,action,detail,created_at) VALUES (?,?,?,?)",
            (market_id, action, detail, utcnow()),
        )

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def record_export(self, packet_id: str, directory: Path, manifest: dict):
        with self.transaction():
            self.db.execute(
                "INSERT INTO exports(packet_id,directory,manifest,created_at) VALUES (?,?,?,?)",
                (packet_id, str(directory), canonical(manifest), utcnow()),
            )
