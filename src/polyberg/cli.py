from __future__ import annotations

import argparse
import sys
from pathlib import Path

from polyberg.account_normalizer import NormalizerError, promote_data_api_positions
from polyberg.adjudicator_builder import write_adjudicator_input
from polyberg.collectors.polymarket_account import (
    AccountImportError,
    write_authenticated_account_snapshot,
    write_public_positions,
)
from polyberg.collectors.polymarket_gamma import GammaCollectorError
from polyberg.config import repo_path
from polyberg.packet_builder import write_packet
from polyberg.price_history import build_price_history_artifact, default_price_history_path
from polyberg.snapshots import build_market_snapshot, default_snapshot_path, diff_snapshots
from polyberg.trade_ticket import build_trade_ticket
from polyberg.validators import (
    ResponseValidationError,
    validate_adjudicator_output,
    validate_model_response,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="polyberg")
    subparsers = parser.add_subparsers(dest="command", required=True)

    packet = subparsers.add_parser("build-packet", help="Build a markdown model context packet.")
    packet.add_argument(
        "--output",
        type=Path,
        default=repo_path("reports", "generated", "packet.md"),
    )
    packet.add_argument("--context-dir", type=Path, default=None)
    packet.add_argument("--snapshot", type=Path, default=None)
    packet.set_defaults(func=command_build_packet)

    validate_response = subparsers.add_parser(
        "validate-response", help="Validate a model JSON response."
    )
    validate_response.add_argument("path", type=Path)
    validate_response.set_defaults(func=command_validate_response)

    validate_adjudicator = subparsers.add_parser(
        "validate-adjudicator", help="Validate an adjudicator JSON response."
    )
    validate_adjudicator.add_argument("path", type=Path)
    validate_adjudicator.set_defaults(func=command_validate_adjudicator)

    adjudicator = subparsers.add_parser(
        "build-adjudicator-input", help="Build a markdown packet for adjudication."
    )
    adjudicator.add_argument("--packet", type=Path, required=True)
    adjudicator.add_argument("--model-output-a", type=Path, required=True)
    adjudicator.add_argument("--model-output-b", type=Path, required=True)
    adjudicator.add_argument("--output", type=Path, required=True)
    adjudicator.set_defaults(func=command_build_adjudicator_input)

    snapshot = subparsers.add_parser("snapshot-markets", help="Write a read-only market snapshot.")
    snapshot.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to data/snapshots/markets_YYYY-MM-DD_HHMM.json.",
    )
    snapshot.add_argument("--context-dir", type=Path, default=None)
    snapshot.set_defaults(func=command_snapshot_markets)

    diff = subparsers.add_parser("diff-snapshots", help="Compare two market snapshots.")
    diff.add_argument("--old", type=Path, required=True)
    diff.add_argument("--new", type=Path, required=True)
    diff.set_defaults(func=command_diff_snapshots)

    ticket = subparsers.add_parser(
        "build-trade-ticket",
        help="Build a human-reviewed trade ticket.",
    )
    ticket.add_argument("--adjudicator-output", type=Path, required=True)
    ticket.add_argument("--output", type=Path, required=True)
    ticket.set_defaults(func=command_build_trade_ticket)

    public_positions = subparsers.add_parser(
        "import-public-positions",
        help="Import read-only public positions by address (data-api.polymarket.com).",
    )
    public_positions.add_argument("--address", type=str, required=True)
    public_positions.add_argument(
        "--output",
        type=Path,
        default=repo_path("reports", "generated", "account", "positions_data_api.json"),
    )
    public_positions.set_defaults(func=command_import_public_positions)

    promote = subparsers.add_parser(
        "promote-positions",
        help="Normalize a data-api positions import and write portfolio_current.yaml.",
    )
    promote.add_argument(
        "--raw",
        type=Path,
        default=repo_path("reports", "generated", "account", "positions_data_api.json"),
        help="Raw positions JSON written by import-public-positions.",
    )
    promote.add_argument(
        "--output",
        type=Path,
        default=repo_path("context", "portfolio_current.yaml"),
    )
    promote.add_argument(
        "--cash",
        type=float,
        default=None,
        help="Override cash_available. Defaults to live_state.yaml's value.",
    )
    promote.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the normalized YAML to stdout instead of writing.",
    )
    promote.set_defaults(func=command_promote_positions)

    account_snapshot = subparsers.add_parser(
        "import-account-snapshot",
        help="Import read-only authenticated account positions, balances, and open orders.",
    )
    account_snapshot.add_argument(
        "--output-dir",
        type=Path,
        default=repo_path("reports", "generated", "account"),
    )
    account_snapshot.set_defaults(func=command_import_account_snapshot)

    price_history = subparsers.add_parser(
        "fetch-price-history",
        help="Fetch per-market CLOB price-history series and high/low windows.",
    )
    price_history.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to context/price_history.json.",
    )
    price_history.add_argument("--context-dir", type=Path, default=None)
    price_history.set_defaults(func=command_fetch_price_history)

    return parser


def command_build_packet(args: argparse.Namespace) -> int:
    path = write_packet(args.output, context_dir=args.context_dir, snapshot_path=args.snapshot)
    print(f"Wrote packet to {path}")
    return 0


def command_validate_response(args: argparse.Namespace) -> int:
    try:
        validate_model_response(args.path)
    except ResponseValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Valid model response: {args.path}")
    return 0


def command_validate_adjudicator(args: argparse.Namespace) -> int:
    try:
        validate_adjudicator_output(args.path)
    except ResponseValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Valid adjudicator output: {args.path}")
    return 0


def command_build_adjudicator_input(args: argparse.Namespace) -> int:
    path = write_adjudicator_input(
        packet_path=args.packet,
        model_output_a=args.model_output_a,
        model_output_b=args.model_output_b,
        output_path=args.output,
    )
    print(f"Wrote adjudicator input to {path}")
    return 0


def command_snapshot_markets(args: argparse.Namespace) -> int:
    output = args.output or default_snapshot_path(repo_path("data", "snapshots"))
    registry_path = None
    if args.context_dir is not None:
        registry_path = args.context_dir / "market_registry.yaml"
    path = build_market_snapshot(output, registry_path=registry_path)
    print(f"Wrote market snapshot to {path}")
    return 0


def command_diff_snapshots(args: argparse.Namespace) -> int:
    print(diff_snapshots(args.old, args.new), end="")
    return 0


def command_build_trade_ticket(args: argparse.Namespace) -> int:
    path = build_trade_ticket(args.adjudicator_output, args.output)
    print(f"Wrote human trade ticket to {path}")
    return 0


def command_import_public_positions(args: argparse.Namespace) -> int:
    try:
        path = write_public_positions(args.address, args.output)
    except AccountImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Wrote public positions import to {path}")
    return 0


def command_import_account_snapshot(args: argparse.Namespace) -> int:
    try:
        paths = write_authenticated_account_snapshot(args.output_dir)
    except AccountImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for path in paths:
        print(f"Wrote authenticated account import to {path}")
    return 0


def command_promote_positions(args: argparse.Namespace) -> int:
    import json as _json

    from polyberg.account_normalizer import (
        _dump_portfolio_yaml,
        _read_existing_thesis_buckets,
        normalize_data_api_positions,
    )
    from polyberg.loaders import load_live_state, load_market_registry

    if not args.raw.exists():
        print(f"Raw positions file not found: {args.raw}", file=sys.stderr)
        return 1
    try:
        raw_doc = _json.loads(args.raw.read_text(encoding="utf-8"))
    except _json.JSONDecodeError as exc:
        print(f"Invalid JSON in {args.raw}: {exc}", file=sys.stderr)
        return 1
    payload = raw_doc.get("payload", raw_doc) if isinstance(raw_doc, dict) else raw_doc

    cash = args.cash
    if cash is None:
        try:
            live = load_live_state()
            cash = float(live.account_snapshot.cash_available)
        except Exception as exc:
            print(f"Could not read cash_available from live_state.yaml: {exc}", file=sys.stderr)
            return 1

    try:
        registry = load_market_registry()
        portfolio, skipped = normalize_data_api_positions(
            payload, registry, cash_available=cash
        )
    except NormalizerError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    thesis = _read_existing_thesis_buckets(args.output)
    if thesis:
        portfolio = portfolio.model_copy(
            update={
                "positions": [
                    p.model_copy(update={"thesis_bucket": thesis.get(p.market_id, "")})
                    for p in portfolio.positions
                ]
            }
        )

    yaml_text = _dump_portfolio_yaml(portfolio)
    if args.dry_run:
        sys.stdout.write(yaml_text)
        if skipped:
            print(f"\n# skipped: {len(skipped)}", file=sys.stderr)
            for s in skipped:
                print(f"#   {s}", file=sys.stderr)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml_text, encoding="utf-8")
    print(f"Wrote canonical portfolio to {args.output}")
    if skipped:
        print(f"Skipped {len(skipped)} positions (not in registry):", file=sys.stderr)
        for s in skipped:
            print(f"  - {s}", file=sys.stderr)
    return 0


def command_fetch_price_history(args: argparse.Namespace) -> int:
    context_dir = args.context_dir or repo_path("context")
    output = args.output or default_price_history_path(context_dir)
    registry_path = context_dir / "market_registry.yaml" if args.context_dir else None
    try:
        path = build_price_history_artifact(output, registry_path=registry_path)
    except GammaCollectorError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Wrote price-history artifact to {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
