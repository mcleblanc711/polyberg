"""Account-free entrypoint. Account code and dotenv load only under `legacy`."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from pydantic import ValidationError

from polyberg.research.models import canonical
from polyberg.research.service import Request, dispatch
from polyberg.research.storage import Store
from polyberg.research.workspace import Workspace


def _db(parser):
    parser.add_argument(
        "--db",
        type=Path,
        default=argparse.SUPPRESS,
        help="Research SQLite path (or POLYBERG_RESEARCH_DB)",
    )


def _selection(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--market")
    group.add_argument("--event")
    group.add_argument("--project")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="polyberg", description="Local public-market research")
    _db(parser)
    root = parser.add_subparsers(dest="command", required=True)
    root.add_parser(
        "legacy", help="Explicit legacy portfolio workspace; append prior CLI arguments"
    )
    research = root.add_parser("research", help="Account-free research workspace")
    _db(research)
    sub = research.add_subparsers(dest="operation", required=True)
    for op in [
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
        "note",
        "verify",
        "rules",
        "annotate",
        "relate",
        "compare",
        "history",
        "price-history",
        "book",
        "rpc",
    ]:
        p = sub.add_parser(op)
        _db(p)
        if op in {"search", "inspect", "follow"}:
            p.add_argument("reference")
        if op == "search":
            p.add_argument("--include-closed", action="store_true")
        if op == "follow":
            p.add_argument("--project", default="default")
        if op in {"list", "refresh"}:
            _selection(p)
        if op == "list":
            p.add_argument("--all", dest="all_markets", action="store_true")
        if op in {
            "show",
            "unfollow",
            "refollow",
            "status",
            "tags",
            "archive",
            "unarchive",
            "note",
            "rules",
            "annotate",
            "relate",
            "compare",
            "history",
            "price-history",
            "book",
        }:
            p.add_argument("market")
        if op == "price-history":
            p.add_argument("--span", choices=["1d", "1w", "1m", "max"], default="1w")
            p.add_argument("--refetch", action="store_true")
        if op == "status":
            p.add_argument("status")
        if op == "tags":
            p.add_argument("tags", nargs="*")
        if op in {"relate", "compare"}:
            p.add_argument("other_market")
        if op in {"note", "annotate", "relate"}:
            p.add_argument("text")
        if op == "note":
            p.add_argument("--category", default="observation")
            p.add_argument("--source", action="append", default=[])
            p.add_argument("--published-at")
            p.add_argument("--observed-at")
        if op == "verify":
            p.add_argument("entry_id", type=int)
        if op == "annotate":
            p.add_argument("--version-id", type=int, required=True)
            p.add_argument("--kind", required=True)
            p.add_argument("--source-url", required=True)
        if op == "relate":
            p.add_argument("--kind", required=True)
            p.add_argument("--source-url")
    projects = sub.add_parser("projects")
    _db(projects)
    project_sub = projects.add_subparsers(dest="project_operation", required=True)
    project_sub.add_parser("list")
    create = project_sub.add_parser("create")
    create.add_argument("project")
    for operation in ("add", "remove"):
        p = project_sub.add_parser(operation)
        p.add_argument("project")
        p.add_argument("market")
    packet = root.add_parser("packet", help="Canonical public research packets")
    _db(packet)
    packet_sub = packet.add_subparsers(dest="packet_operation", required=True)
    for operation in ("build", "render"):
        p = packet_sub.add_parser(operation)
        _db(p)
        if operation == "build":
            _selection(p)
        else:
            p.add_argument("packet_id")
        p.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "legacy":
        from polyberg.legacy_cli import main as legacy_main

        return legacy_main(arguments[1:])
    args = vars(build_parser().parse_args(arguments))
    db = args.pop("db", None)
    command = args.pop("command")
    output = args.pop("output_dir", None)
    rpc = args.get("operation") == "rpc"
    try:
        if rpc:
            request = Request.model_validate_json(sys.stdin.read(2_000_001))
        else:
            if command == "packet":
                args["operation"] = (
                    "packet" if args.pop("packet_operation") == "build" else "render"
                )
            if args.get("operation") == "price-history":
                args["operation"] = "price_history"
            if args.get("operation") == "projects":
                action = args.pop("project_operation")
                args["operation"] = "projects" if action == "list" else f"project_{action}"
            if args.get("operation") == "note":
                published, observed = args.pop("published_at"), args.pop("observed_at")
                args["sources"] = [
                    {"url": url, "published_at": published, "observed_at": observed}
                    for url in args.pop("source")
                ]
            request = Request.model_validate(args)
        with Store(db) as store:
            result = dispatch(Workspace(store), request, output_dir=output)
        print(canonical(result), end="")
        return 0
    except ValidationError:
        message = "Invalid research request or public data shape"
    except sqlite3.Error:
        message = "Research database operation failed"
    except (ValueError, OSError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Research file operation failed"
    if rpc:
        print(json.dumps({"error": message}))
    else:
        print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
