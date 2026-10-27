"""Typed operation boundary shared by CLI and Electron's structured stdin protocol."""

from __future__ import annotations

import difflib
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, model_validator

from polyberg.config import get_max_context_age_hours
from polyberg.research.models import HistorySpan, RulesVersion, Source, StrictModel
from polyberg.research.packets import export_packet, freeze, load_frozen, market_warnings, render
from polyberg.research.workspace import Workspace


class Request(StrictModel):
    operation: Literal[
        "init",
        "search",
        "inspect",
        "follow",
        "list",
        "show",
        "refresh",
        "unfollow",
        "refollow",
        "status",
        "tags",
        "archive",
        "unarchive",
        "projects",
        "project_create",
        "project_add",
        "project_remove",
        "note",
        "verify",
        "rules",
        "annotate",
        "relate",
        "compare",
        "history",
        "price_history",
        "book",
        "packet",
        "render",
    ]
    reference: str | None = Field(default=None, max_length=2000)
    market: str | None = None
    event: str | None = None
    project: str | None = None
    all_markets: bool = False
    include_closed: bool = False
    status: str | None = None
    tags: list[str] = Field(default_factory=list)
    category: str | None = None
    text: str | None = Field(default=None, max_length=200000)
    sources: list[Source] = Field(default_factory=list)
    entry_id: int | None = None
    version_id: int | None = None
    kind: str | None = None
    source_url: str | None = None
    other_market: str | None = None
    packet_id: str | None = None
    span: HistorySpan | None = None
    refetch: bool = False

    @model_validator(mode="after")
    def selection(self):
        if (
            self.operation in {"list", "packet", "refresh"}
            and sum(bool(value) for value in [self.market, self.event, self.project]) > 1
        ):
            raise ValueError("Select one market, event, or project")
        return self


def required(value):
    if value is None or value == "":
        raise ValueError("Required research parameter missing")
    return value


_RULES_FIELDS = ("api_url", "page_url", "resolution_source", "resolution_status")


def rules_changes(versions: list[RulesVersion]) -> dict[str, dict]:
    """Per version: verbatim text diff and changed public fields against its predecessor."""
    changes = {}
    for before, after in zip(versions, versions[1:], strict=False):
        changes[str(after.rules_version_id)] = {
            "previous_version_id": before.rules_version_id,
            "text_diff": list(
                difflib.unified_diff(
                    before.text.splitlines(),
                    after.text.splitlines(),
                    f"v{before.rules_version_id}",
                    f"v{after.rules_version_id}",
                    lineterm="",
                )
            ),
            "fields": {
                field: [getattr(before, field), getattr(after, field)]
                for field in _RULES_FIELDS
                if getattr(before, field) != getattr(after, field)
            },
        }
    return changes


def dispatch(workspace: Workspace, request: Request, *, output_dir=None) -> dict:
    r = Request.model_validate(request.model_dump())
    op = r.operation
    mid = r.market
    if op == "init":
        return {"schema_version": 1, "projects": workspace.projects()}
    if op == "search":
        return workspace.public.search(required(r.reference), r.include_closed).model_dump()
    if op == "inspect":
        return workspace.public.resolve(required(r.reference)).model_dump()
    if op == "follow":
        return {"market_ids": workspace.follow(required(r.reference), r.project or "default")}
    if op == "list":
        now, threshold = datetime.now(UTC), get_max_context_age_hours()
        ids = workspace.select(
            market=mid, event=r.event, project=r.project, all_markets=r.all_markets
        )
        markets = [workspace.show(m) for m in ids]
        for market in markets:
            market.warnings = market_warnings(market, now, threshold)
        event_ids = {m.identification.event_id for m in markets}
        # Viewer context travels beside the packet-shaped markets, never inside them.
        activity = {m: workspace.activity(m) for m in ids}
        return {
            "markets": [m.model_dump() for m in markets],
            "projects": workspace.projects(),
            "activity": {m: a.model_dump() for m, a in activity.items() if a},
            "events": {
                e.event_id: {
                    "title": e.title,
                    "description": e.description,
                    "page_url": e.page_url,
                    "retrieved_at": e.retrieved_at,
                }
                for e in workspace.events()
                if e.event_id in event_ids
            },
        }
    if op == "show":
        market = workspace.show(required(mid))
        market.warnings = market_warnings(market, datetime.now(UTC), get_max_context_age_hours())
        return market.model_dump()
    if op == "price_history":
        return workspace.price_history(required(mid), r.span or "1w", r.refetch).model_dump()
    if op == "book":
        return workspace.book(required(mid)).model_dump()
    if op == "refresh":
        if r.event:
            return workspace.refresh_event(r.event)
        return workspace.refresh(workspace.select(market=mid, project=r.project))
    if op in {"unfollow", "refollow"}:
        workspace.set_followed(required(mid), op == "refollow")
    elif op == "status":
        workspace.set_status(required(mid), required(r.status))
    elif op == "archive":
        workspace.set_status(required(mid), "archived")
    elif op == "unarchive":
        workspace.unarchive(required(mid))
    elif op == "tags":
        workspace.tags(required(mid), r.tags)
    elif op == "projects":
        return {"projects": workspace.projects()}
    elif op == "project_create":
        workspace.create_project(required(r.project))
    elif op in {"project_add", "project_remove"}:
        workspace.membership(required(mid), required(r.project), op == "project_add")
    elif op == "note":
        return {
            "entry_id": workspace.add_entry(
                required(mid), required(r.category), required(r.text), r.sources
            )
        }
    elif op == "verify":
        workspace.verify_entry(required(r.entry_id))
    elif op == "rules":
        versions = workspace.rules_history(required(mid))
        return {
            "versions": [v.model_dump() for v in versions],
            "changes": rules_changes(versions),
            "observations": workspace.store.all(
                "SELECT rules_version_id,retrieved_at FROM rules_observations WHERE market_id=? "
                "ORDER BY observation_id",
                (required(mid),),
            ),
        }
    elif op == "annotate":
        workspace.annotate(
            required(mid),
            required(r.version_id),
            required(r.kind),
            required(r.text),
            required(r.source_url),
        )
    elif op == "relate":
        workspace.relate(
            required(mid),
            required(r.other_market),
            required(r.kind),
            required(r.text),
            r.source_url,
        )
    elif op == "history":
        workspace.require(required(mid))
        return {
            "history": workspace.store.all(
                "SELECT action,detail,created_at FROM workspace_history WHERE "
                "market_id=? ORDER BY history_id",
                (mid,),
            )
        }
    elif op in {"packet", "render", "compare"}:
        if op == "render":
            frozen = load_frozen(workspace, required(r.packet_id))
        else:
            ids = [required(mid), required(r.other_market)] if op == "compare" else None
            frozen = freeze(workspace, market=mid, event=r.event, project=r.project, market_ids=ids)
        result = frozen.model_dump()
        result["contents"] = render(frozen)
        if op != "compare":
            result["export"] = export_packet(workspace, frozen, output_dir)
        return result
    else:
        raise ValueError("Unsupported research operation")
    return {"ok": True}
