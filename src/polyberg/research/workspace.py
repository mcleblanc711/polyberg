"""Research operations; network calls finish before database transactions begin."""

from __future__ import annotations

import json
from typing import get_args

from polyberg.research.models import (
    SYMMETRIC,
    Annotation,
    AnnotationKind,
    Category,
    CollectedMarket,
    Discovery,
    Entry,
    Event,
    Identification,
    Quote,
    RelationKind,
    Relationship,
    ResearchMarket,
    RulesInput,
    RulesVersion,
    Snapshot,
    Source,
    Status,
    canonical,
    digest,
    utcnow,
)
from polyberg.research.public import PublicClient, PublicDataError
from polyberg.research.storage import Store


class Workspace:
    def __init__(self, store: Store, public: PublicClient | None = None):
        self.store = store
        self.db = store.db
        self.public = public or PublicClient()

    def require(self, market_id: str) -> dict:
        row = self.store.one("SELECT * FROM markets WHERE market_id=?", (market_id,))
        if row is None:
            raise ValueError("Market is not in the research workspace")
        return row

    def projects(self) -> list[dict]:
        return self.store.all("SELECT name,created_at FROM projects ORDER BY name")

    def project(self, name: str) -> int:
        row = self.store.one("SELECT project_id FROM projects WHERE name=?", (name,))
        if row is None:
            raise ValueError("Unknown research project")
        return row["project_id"]

    def create_project(self, name: str) -> None:
        if not name.strip() or len(name) > 120:
            raise ValueError("Project name must contain 1–120 characters")
        with self.store.transaction():
            self.db.execute(
                "INSERT OR IGNORE INTO projects(name,created_at) VALUES (?,?)", (name, utcnow())
            )

    def membership(self, market_id: str, project: str, add: bool = True) -> None:
        self.require(market_id)
        pid = self.project(project)
        with self.store.transaction():
            if add:
                self.db.execute(
                    "INSERT OR IGNORE INTO project_markets VALUES (?,?)", (pid, market_id)
                )
            else:
                self.db.execute(
                    "DELETE FROM project_markets WHERE project_id=? AND market_id=?",
                    (pid, market_id),
                )
            self.store.history(market_id, "project_add" if add else "project_remove", project)

    def ingest(
        self,
        discovery: Discovery,
        *,
        follow: bool = False,
        project: str = "default",
        started_at: str | None = None,
    ) -> list[str]:
        """Accept only validated allowlisted research models, never a raw API object."""
        discovery = Discovery.model_validate(discovery.model_dump())
        pid = self.project(project)
        with self.store.transaction():
            for event in discovery.events:
                if not event.contracts and self.store.one(
                    "SELECT 1 FROM events WHERE event_id=?", (event.event_id,)
                ):
                    continue  # Embedded market summaries cannot replace a full event retrieval.
                self.db.execute(
                    "INSERT INTO events VALUES (?,?) ON CONFLICT(event_id) DO UPDATE "
                    "SET data=excluded.data",
                    (event.event_id, canonical(event)),
                )
            for market in discovery.markets:
                self._save_market(market, follow, pid, started_at or market.retrieved_at)
        return [m.identification.market_id for m in discovery.markets]

    def _save_market(self, market: CollectedMarket, follow: bool, project_id: int, started: str):
        identity, at = market.identification, market.retrieved_at
        mid = identity.market_id
        self._retain_quotes(market)
        self.db.execute(
            "INSERT INTO markets(market_id,event_id,identification,created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(market_id) DO UPDATE SET "
            "event_id=COALESCE(excluded.event_id,markets.event_id),identification=excluded.identification",
            (mid, identity.event_id, canonical(identity), at),
        )
        if follow:
            self.db.execute("UPDATE markets SET followed=1 WHERE market_id=?", (mid,))
            self.db.execute("INSERT OR IGNORE INTO project_markets VALUES (?,?)", (project_id, mid))
            self.store.history(mid, "follow", str(project_id))
        for outcome in identity.outcomes:
            self.db.execute(
                "INSERT INTO outcomes VALUES (?,?,?,?,?,?,?) ON CONFLICT(outcome_id) DO UPDATE SET "
                "label=excluded.label,token_id=excluded.token_id,position_id=excluded.position_id,"
                "asset_id=excluded.asset_id",
                (
                    outcome.outcome_id,
                    mid,
                    outcome.index,
                    outcome.label,
                    outcome.token_id,
                    outcome.position_id,
                    outcome.asset_id,
                ),
            )
        previous = self.store.one(
            "SELECT rules_version_id FROM rules_observations WHERE market_id=? "
            "ORDER BY observation_id DESC LIMIT 1",
            (mid,),
        )
        version_id = None
        if market.rules:
            rules = market.rules
            content_hash = digest(canonical(rules))
            self.db.execute(
                "INSERT OR IGNORE INTO "
                "rules_versions(market_id,content_hash,data,first_retrieved_at) "
                "VALUES (?,?,?,?)",
                (mid, content_hash, canonical(rules), at),
            )
            version_id = self.store.one(
                "SELECT rules_version_id FROM rules_versions WHERE market_id=? AND content_hash=?",
                (mid, content_hash),
            )["rules_version_id"]
        if previous and previous["rules_version_id"] != version_id:
            self.db.execute(
                "UPDATE rules_annotations SET needs_review=1 WHERE rules_version_id IN "
                "(SELECT rules_version_id FROM rules_versions WHERE market_id=?)",
                (mid,),
            )
        self.db.execute(
            "INSERT INTO "
            "rules_observations(market_id,rules_version_id,retrieved_at) VALUES (?,?,?)",
            (mid, version_id, at),
        )
        partial = bool(market.warnings or any(q.warnings for q in market.quotes))
        attempt = self.db.execute(
            "INSERT INTO refresh_attempts(market_id,reference,started_at,finished_at,status) "
            "VALUES (?,?,?,?,?)",
            (mid, f"market:{mid}", started, utcnow(), "partial" if partial else "success"),
        ).lastrowid
        snapshot = self.db.execute(
            "INSERT INTO market_snapshots(market_id,attempt_id,rules_version_id,retrieved_at,"
            "identification,warnings) VALUES (?,?,?,?,?,?)",
            (mid, attempt, version_id, at, canonical(identity), canonical(market.warnings)),
        ).lastrowid
        for q in market.quotes:
            self.db.execute(
                "INSERT INTO outcome_quotes VALUES (?,?,?)", (snapshot, q.outcome_id, canonical(q))
            )
        self.db.execute(
            "UPDATE markets SET last_attempt_at=?,last_success_at=? WHERE market_id=?",
            (at, at, mid),
        )

    def follow(self, reference: str, project: str = "default") -> list[str]:
        self.project(project)  # Validate before network work.
        started = utcnow()
        try:
            discovery = self.public.resolve(reference)
            for market in discovery.markets:
                self.public.collect_quotes(market)
        except PublicDataError:
            self.failure(reference, started)
            raise
        return self.ingest(discovery, follow=True, project=project, started_at=started)

    def failure(self, reference: str, started: str, market_id: str | None = None):
        # Reference is user input, not upstream exception content. Diagnostics are fixed.
        with self.store.transaction():
            self.db.execute(
                "INSERT INTO "
                "refresh_attempts(market_id,reference,started_at,finished_at,status,message) "
                "VALUES (?,?,?,?,?,?)",
                (
                    market_id,
                    reference,
                    started,
                    utcnow(),
                    "failed",
                    "Public metadata refresh failed",
                ),
            )
            if market_id:
                self.db.execute(
                    "UPDATE markets SET last_attempt_at=? WHERE market_id=?", (started, market_id)
                )

    def refresh(self, market_ids: list[str]) -> dict:
        for mid in market_ids:
            self.require(mid)
        refreshed, failed = [], []
        for mid in market_ids:
            started = utcnow()
            try:
                discovery = self.public.resolve(f"market:{mid}")
                if {m.identification.market_id for m in discovery.markets} != {mid}:
                    raise PublicDataError("Public identity changed")
                for market in discovery.markets:
                    self.public.collect_quotes(market)
            except PublicDataError:
                self.failure(f"market:{mid}", started, mid)
                failed.append(mid)
                continue
            self.ingest(discovery, started_at=started)
            refreshed.append(mid)
        return {"refreshed": refreshed, "failed": failed}

    def refresh_event(self, event_id: str) -> dict:
        started = utcnow()
        known = self.select(event=event_id)
        try:
            discovery = self.public.resolve(f"event:{event_id}")
            for market in discovery.markets:
                self.public.collect_quotes(market)
        except PublicDataError:
            for mid in known:
                self.failure(f"event:{event_id}", started, mid)
            return {"refreshed": [], "failed": known}
        ids = self.ingest(discovery, started_at=started)
        return {"refreshed": ids, "failed": []}

    def set_followed(self, market_id: str, followed: bool):
        self.require(market_id)
        with self.store.transaction():
            self.db.execute(
                "UPDATE markets SET followed=? WHERE market_id=?", (int(followed), market_id)
            )
            self.store.history(market_id, "follow" if followed else "unfollow", "")

    def set_status(self, market_id: str, status: str):
        row = self.require(market_id)
        if status not in get_args(Status):
            raise ValueError("Unsupported research status")
        if row["status"] == status:
            return
        with self.store.transaction():
            self.db.execute(
                "UPDATE markets SET status=?,previous_status=? WHERE market_id=?",
                (status, row["status"], market_id),
            )
            self.store.history(market_id, "status", status)

    def unarchive(self, market_id: str):
        row = self.require(market_id)
        if row["status"] == "archived":
            self.set_status(market_id, row["previous_status"] or "discovered")

    def tags(self, market_id: str, tags: list[str]):
        self.require(market_id)
        if any(not tag.strip() or len(tag) > 80 for tag in tags):
            raise ValueError("Tags must contain 1–80 characters")
        with self.store.transaction():
            self.db.execute("DELETE FROM tags WHERE market_id=?", (market_id,))
            self.db.executemany(
                "INSERT INTO tags VALUES (?,?)", [(market_id, tag) for tag in sorted(set(tags))]
            )
            self.store.history(market_id, "tags", canonical(tags))

    def add_entry(self, market_id: str, category: str, text: str, sources: list[Source]) -> int:
        self.require(market_id)
        if category not in get_args(Category) or not text.strip():
            raise ValueError("Entry requires a supported category and nonempty text")
        sources = [Source.model_validate(s.model_dump()) for s in sources]
        with self.store.transaction():
            eid = self.db.execute(
                "INSERT INTO research_entries(market_id,category,text,created_at) VALUES (?,?,?,?)",
                (market_id, category, text, utcnow()),
            ).lastrowid
            for source in sources:
                data = canonical(source)
                self.db.execute(
                    "INSERT OR IGNORE INTO sources(content_hash,data) VALUES (?,?)",
                    (digest(data), data),
                )
                sid = self.store.one(
                    "SELECT source_id FROM sources WHERE content_hash=?", (digest(data),)
                )["source_id"]
                self.db.execute("INSERT OR IGNORE INTO entry_sources VALUES (?,?)", (eid, sid))
            self.store.history(market_id, "entry_added", str(eid))
        return eid

    def verify_entry(self, entry_id: int):
        entry = self.store.one("SELECT * FROM research_entries WHERE entry_id=?", (entry_id,))
        if not entry or entry["category"] != "observation":
            raise ValueError("Only source-supported observations can be marked verified")
        if not self.store.one("SELECT source_id FROM entry_sources WHERE entry_id=?", (entry_id,)):
            raise ValueError("Verification requires source references")
        with self.store.transaction():
            self.db.execute(
                "UPDATE research_entries SET verified_at=? WHERE entry_id=?", (utcnow(), entry_id)
            )
            self.store.history(entry["market_id"], "verified", str(entry_id))

    def annotate(self, market_id: str, version_id: int, kind: str, text: str, source_url: str):
        self.require(market_id)
        if kind not in get_args(AnnotationKind) or not text.strip():
            raise ValueError("Annotation requires a supported kind and nonempty text")
        Source(url=source_url)
        if not self.store.one(
            "SELECT 1 FROM rules_versions WHERE market_id=? AND rules_version_id=?",
            (market_id, version_id),
        ):
            raise ValueError("Rules version does not belong to this market")
        latest = self.store.one(
            "SELECT rules_version_id FROM rules_observations WHERE market_id=? "
            "ORDER BY observation_id DESC LIMIT 1",
            (market_id,),
        )
        with self.store.transaction():
            self.db.execute(
                "INSERT INTO "
                "rules_annotations(rules_version_id,kind,text,source_url,created_at,needs_review) "
                "VALUES (?,?,?,?,?,?)",
                (
                    version_id,
                    kind,
                    text,
                    source_url,
                    utcnow(),
                    int(latest["rules_version_id"] != version_id),
                ),
            )

    def rules_history(self, market_id: str) -> list[RulesVersion]:
        self.require(market_id)
        versions = self.store.all(
            "SELECT * FROM rules_versions WHERE market_id=? ORDER BY rules_version_id", (market_id,)
        )
        return [self.rules_version(row) for row in versions]

    def rules_version(self, row: dict) -> RulesVersion:
        vid = row["rules_version_id"]
        annotations = self.store.all(
            "SELECT * FROM rules_annotations WHERE rules_version_id=? ORDER BY annotation_id",
            (vid,),
        )
        for a in annotations:
            a["needs_review"] = bool(a["needs_review"])
        return RulesVersion(
            **RulesInput.model_validate_json(row["data"]).model_dump(),
            rules_version_id=vid,
            first_retrieved_at=row["first_retrieved_at"],
            observations=[
                r["retrieved_at"]
                for r in self.store.all(
                    "SELECT retrieved_at FROM rules_observations WHERE "
                    "rules_version_id=? ORDER BY observation_id",
                    (vid,),
                )
            ],
            annotations=[Annotation.model_validate(a) for a in annotations],
        )

    def relate(
        self, first: str, second: str, kind: str, explanation: str, source_url: str | None = None
    ):
        self.require(first)
        self.require(second)
        if first == second or kind not in get_args(RelationKind) or not explanation.strip():
            raise ValueError("Relationship requires distinct markets, a kind, and an explanation")
        if source_url:
            Source(url=source_url)
        if kind in SYMMETRIC:
            first, second = sorted([first, second])
        with self.store.transaction():
            self.db.execute(
                "INSERT INTO "
                "relationships(from_market,to_market,kind,explanation,source_url,created_at) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(from_market,to_market,kind) DO UPDATE SET "
                "explanation=excluded.explanation,source_url=excluded.source_url",
                (first, second, kind, explanation, source_url, utcnow()),
            )

    def select(
        self,
        *,
        market: str | None = None,
        event: str | None = None,
        project: str | None = None,
        all_markets: bool = False,
    ) -> list[str]:
        if sum(bool(v) for v in [market, event, project]) > 1:
            raise ValueError("Select one market, event, or project")
        if market:
            self.require(market)
            return [market]
        if project:
            pid = self.project(project)
            rows = self.store.all(
                "SELECT market_id FROM project_markets WHERE project_id=? ORDER BY market_id",
                (pid,),
            )
        elif event:
            rows = self.store.all(
                "SELECT market_id FROM markets WHERE event_id=? ORDER BY market_id", (event,)
            )
            if not rows and not self.store.one("SELECT 1 FROM events WHERE event_id=?", (event,)):
                raise ValueError("Unknown research event")
        else:
            rows = self.store.all(
                "SELECT market_id FROM markets "
                + ("" if all_markets else "WHERE followed=1 AND status!='archived' ")
                + "ORDER BY market_id"
            )
        return [r["market_id"] for r in rows]

    def show(self, market_id: str) -> ResearchMarket:
        row = self.require(market_id)
        identity = Identification.model_validate_json(row["identification"])
        identity.event_id = row["event_id"]
        snap = self.store.one(
            "SELECT * FROM market_snapshots WHERE market_id=? ORDER BY snapshot_id DESC LIMIT 1",
            (market_id,),
        )
        snapshot, rules = None, None
        if snap:
            snapshot = Snapshot(
                snapshot_id=snap["snapshot_id"],
                retrieved_at=snap["retrieved_at"],
                rules_version_id=snap["rules_version_id"],
                warnings=json.loads(snap["warnings"]),
                quotes=[
                    Quote.model_validate_json(q["data"])
                    for q in self.store.all(
                        "SELECT data FROM outcome_quotes WHERE snapshot_id=? ORDER BY outcome_id",
                        (snap["snapshot_id"],),
                    )
                ],
            )
            if snap["rules_version_id"]:
                rules = self.rules_version(
                    self.store.one(
                        "SELECT * FROM rules_versions WHERE rules_version_id=?",
                        (snap["rules_version_id"],),
                    )
                )
        entries = []
        for entry in self.store.all(
            "SELECT * FROM research_entries WHERE market_id=? ORDER BY entry_id", (market_id,)
        ):
            entries.append(
                Entry(
                    entry_id=entry["entry_id"],
                    category=entry["category"],
                    text=entry["text"],
                    created_at=entry["created_at"],
                    verified_at=entry["verified_at"],
                    sources=[
                        Source.model_validate_json(s["data"])
                        for s in self.store.all(
                            "SELECT s.data FROM sources s JOIN entry_sources es USING(source_id) "
                            "WHERE es.entry_id=? ORDER BY s.source_id",
                            (entry["entry_id"],),
                        )
                    ],
                )
            )
        attempt = self.store.one(
            "SELECT status FROM refresh_attempts WHERE market_id=? ORDER BY "
            "attempt_id DESC LIMIT 1",
            (market_id,),
        )
        warnings = (
            ["Latest metadata refresh failed; historical snapshot retained"]
            if attempt and attempt["status"] == "failed"
            else []
        )
        return ResearchMarket(
            identification=identity,
            status=row["status"],
            followed=bool(row["followed"]),
            tags=[
                t["tag"]
                for t in self.store.all(
                    "SELECT tag FROM tags WHERE market_id=? ORDER BY tag", (market_id,)
                )
            ],
            projects=[
                p["name"]
                for p in self.store.all(
                    "SELECT p.name FROM projects p JOIN project_markets pm USING(project_id) "
                    "WHERE pm.market_id=? ORDER BY p.name",
                    (market_id,),
                )
            ],
            snapshot=snapshot,
            rules=rules,
            entries=entries,
            relationships=[
                Relationship.model_validate(r)
                for r in self.store.all(
                    "SELECT * FROM relationships WHERE from_market=? OR to_market=? "
                    "ORDER BY relationship_id",
                    (market_id, market_id),
                )
            ],
            last_attempt_at=row["last_attempt_at"],
            last_success_at=row["last_success_at"],
            warnings=warnings,
            annotations_for_review=[
                Annotation.model_validate({**a, "needs_review": bool(a["needs_review"])})
                for a in self.store.all(
                    "SELECT a.* FROM rules_annotations a JOIN rules_versions v "
                    "USING(rules_version_id) WHERE v.market_id=? AND a.needs_review=1 "
                    "ORDER BY annotation_id",
                    (market_id,),
                )
            ],
        )

    def _retain_quotes(self, market: CollectedMarket) -> None:
        """A failed component read keeps the last observed value and its original timestamp."""
        previous = self.store.one(
            "SELECT snapshot_id,identification FROM market_snapshots WHERE market_id=? "
            "ORDER BY snapshot_id DESC LIMIT 1",
            (market.identification.market_id,),
        )
        if not previous:
            return
        identity = Identification.model_validate_json(previous["identification"])
        assets = {o.outcome_id: o.asset_id for o in identity.outcomes}
        current = {o.outcome_id: o.asset_id for o in market.identification.outcomes}
        quotes = {
            q.outcome_id: q
            for q in [
                Quote.model_validate_json(row["data"])
                for row in self.store.all(
                    "SELECT data FROM outcome_quotes WHERE snapshot_id=?",
                    (previous["snapshot_id"],),
                )
            ]
        }
        components = [
            ("displayed_at", ["displayed_price"]),
            ("book_retrieved_at", ["best_bid", "best_ask", "book_timestamp"]),
            ("midpoint_retrieved_at", ["midpoint"]),
            ("last_trade_retrieved_at", ["last_trade"]),
        ]
        for q in market.quotes:
            old = quotes.get(q.outcome_id)
            if not old or assets.get(q.outcome_id) != current.get(q.outcome_id):
                continue
            for timestamp, fields in components:
                if getattr(q, timestamp) is None and getattr(old, timestamp) is not None:
                    setattr(q, timestamp, getattr(old, timestamp))
                    for field in fields:
                        setattr(q, field, getattr(old, field))
                    q.warnings.append(f"Historical {fields[0]} retained after failed public read")
                    q.source_urls = sorted(set(q.source_urls + old.source_urls))

    def events(self) -> list[Event]:
        return [
            Event.model_validate_json(e["data"])
            for e in self.store.all("SELECT data FROM events ORDER BY event_id")
        ]
