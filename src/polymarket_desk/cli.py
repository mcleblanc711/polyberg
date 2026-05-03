from __future__ import annotations

import argparse
import sys
from pathlib import Path

from polymarket_desk.adjudicator_builder import write_adjudicator_input
from polymarket_desk.config import repo_path
from polymarket_desk.packet_builder import write_packet
from polymarket_desk.snapshots import build_market_snapshot, default_snapshot_path, diff_snapshots
from polymarket_desk.trade_ticket import build_trade_ticket
from polymarket_desk.validators import (
    ResponseValidationError,
    validate_adjudicator_output,
    validate_model_response,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="polymarket-desk")
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
