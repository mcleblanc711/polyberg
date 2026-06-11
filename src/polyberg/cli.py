from __future__ import annotations

import argparse
import sys
from pathlib import Path

from polyberg.account_normalizer import NormalizerError
from polyberg.adjudicator_builder import write_adjudicator_input
from polyberg.collectors.polymarket_account import (
    AccountImportError,
    write_authenticated_account_snapshot,
    write_public_positions,
)
from polyberg.collectors.polymarket_clob_auth import load_clob_credentials_from_env
from polyberg.collectors.polymarket_clob_balance import write_clob_balance
from polyberg.collectors.polymarket_clob_orders import write_clob_open_orders
from polyberg.collectors.polymarket_gamma import GammaCollectorError
from polyberg.config import load_repo_dotenv, repo_path
from polyberg.packet_builder import write_model_packets, write_packet
from polyberg.packet_builder.api import TARGETS
from polyberg.paste_import import PasteImportError, import_paste
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

    ladder_group = subparsers.add_parser("ladder", help="Ladder order management.")
    ladder_sub = ladder_group.add_subparsers(dest="ladder_command", required=True)

    ladder_plan = ladder_sub.add_parser(
        "plan",
        help="Diff target ladders vs live orders and print a reconciliation plan.",
    )
    ladder_plan.add_argument("--target", type=Path, default=None, help="Target ladders YAML path.")
    ladder_plan.add_argument(
        "--live-from",
        type=Path,
        default=None,
        dest="live_from",
        help="Import-clob-orders JSON artifact to use instead of a live CLOB fetch.",
    )
    ladder_plan.add_argument(
        "--cash",
        type=float,
        default=None,
        help="Override available cash (USD). Falls back to live CLOB fetch then portfolio yaml.",
    )
    ladder_plan.add_argument("--price-tolerance", type=float, default=None, dest="price_tolerance")
    ladder_plan.add_argument(
        "--shares-tolerance", type=float, default=None, dest="shares_tolerance"
    )
    ladder_plan.add_argument(
        "--manage-all",
        action="store_true",
        default=False,
        dest="manage_all",
        help="Cancel live orders outside managed keys (not just those on managed keys).",
    )
    ladder_plan.add_argument(
        "--no-paste",
        action="store_true",
        default=False,
        dest="no_paste",
        help="Suppress the pipe-delimited paste block.",
    )
    ladder_plan.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="as_json",
        help="Emit the plan as machine-readable JSON (for the GUI) instead of markdown.",
    )
    ladder_plan.set_defaults(func=command_ladder_plan)

    ladder_execute = ladder_sub.add_parser(
        "execute",
        help="Build a fresh plan, then walk it with per-action y/n confirmation "
        "(cancels via API, placements as manual paste lines).",
    )
    ladder_execute.add_argument(
        "--target", type=Path, default=None, help="Target ladders YAML path."
    )
    ladder_execute.add_argument(
        "--live-from",
        type=Path,
        default=None,
        dest="live_from",
        help="Import-clob-orders JSON artifact to use instead of a live CLOB fetch.",
    )
    ladder_execute.add_argument(
        "--cash",
        type=float,
        default=None,
        help="Override available cash (USD). Falls back to live CLOB fetch then portfolio yaml.",
    )
    ladder_execute.add_argument(
        "--price-tolerance", type=float, default=None, dest="price_tolerance"
    )
    ladder_execute.add_argument(
        "--shares-tolerance", type=float, default=None, dest="shares_tolerance"
    )
    ladder_execute.add_argument(
        "--manage-all",
        action="store_true",
        default=False,
        dest="manage_all",
        help="Cancel live orders outside managed keys (not just those on managed keys).",
    )
    ladder_execute.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Order log jsonl path. Default: live/order_log.jsonl.",
    )
    ladder_execute.set_defaults(func=command_ladder_execute)

    # GUI-support subcommands: each performs exactly one confirmed action so the
    # GUI's per-action confirm modal stays the human gate (mirrors `execute`).
    ladder_cancel = ladder_sub.add_parser(
        "cancel",
        help="Cancel a single open order by id (non-interactive; GUI confirms first).",
    )
    ladder_cancel.add_argument("--order-id", required=True, dest="order_id")
    ladder_cancel.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Order log jsonl path. Default: live/order_log.jsonl.",
    )
    ladder_cancel.set_defaults(func=command_ladder_cancel)

    ladder_preflight = ladder_sub.add_parser(
        "preflight",
        help="Fire GET /balance-allowance/update (required after closes before new orders).",
    )
    ladder_preflight.set_defaults(func=command_ladder_preflight)

    ladder_record = ladder_sub.add_parser(
        "record-manual",
        help="Log a manually-placed order as manual_confirmed (GUI 'MARK PLACED').",
    )
    ladder_record.add_argument("--market", required=True, dest="market_id")
    ladder_record.add_argument("--outcome", required=True, choices=["YES", "NO"])
    ladder_record.add_argument("--side", required=True, choices=["BUY", "SELL"])
    ladder_record.add_argument("--price", required=True, type=float)
    ladder_record.add_argument("--shares", required=True, type=float)
    ladder_record.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Order log jsonl path. Default: live/order_log.jsonl.",
    )
    ladder_record.set_defaults(func=command_ladder_record_manual)

    packet = subparsers.add_parser("build-packet", help="Build a markdown model context packet.")
    packet.add_argument(
        "--output",
        type=Path,
        default=repo_path("reports", "generated", "packet.md"),
    )
    packet.add_argument("--context-dir", type=Path, default=None)
    packet.add_argument("--snapshot", type=Path, default=None)
    packet.set_defaults(func=command_build_packet)

    packet_group = subparsers.add_parser(
        "packet", help="Model-specific research packet exports (GPT / Claude)."
    )
    packet_sub = packet_group.add_subparsers(dest="packet_command", required=True)
    packet_build = packet_sub.add_parser(
        "build", help="Build GPT and/or Claude research packets from shared local state."
    )
    packet_build.add_argument(
        "--target",
        choices=[*TARGETS, "all"],
        default="all",
        help="Which model packet(s) to render. Default: all.",
    )
    packet_build.add_argument(
        "--output-dir",
        type=Path,
        default=repo_path("dist", "packets"),
        help="Directory for the rendered packets. Default: dist/packets/.",
    )
    packet_build.add_argument("--context-dir", type=Path, default=None)
    packet_build.add_argument("--snapshot", type=Path, default=None)
    packet_build.set_defaults(func=command_packet_build)

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
    public_positions.add_argument(
        "--balance-output",
        type=Path,
        default=repo_path("reports", "generated", "account", "usdc_balance.json"),
        help="Sibling JSON for the wallet's CLOB collateral (USDC) balance.",
    )
    public_positions.add_argument(
        "--skip-balance",
        action="store_true",
        help=(
            "Skip the CLOB collateral-balance fetch (positions only). The "
            "balance fetch needs POLYMARKET_CLOB_* credentials; if they are "
            "absent it skips automatically with a non-fatal warning."
        ),
    )
    public_positions.set_defaults(func=command_import_public_positions)

    promote = subparsers.add_parser(
        "promote-positions",
        help="Normalize a data-api positions import and write portfolio_current.local.yaml.",
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
        default=repo_path("context", "portfolio_current.local.yaml"),
        help=(
            "Where to write real state. Defaults to the gitignored "
            "context/portfolio_current.local.yaml overlay so live holdings never "
            "land in the tracked sample file."
        ),
    )
    promote.add_argument(
        "--cash",
        type=float,
        default=None,
        help=(
            "Override cash_available. Defaults to the CLOB usdc_balance.json "
            "artifact if present, then live_state.yaml's value."
        ),
    )
    promote.add_argument(
        "--balance",
        type=Path,
        default=repo_path("reports", "generated", "account", "usdc_balance.json"),
        help="Path to the CLOB usdc_balance.json artifact (read for cash fallback).",
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

    promote_orders = subparsers.add_parser(
        "promote-orders",
        help="Normalize a CLOB open-orders import and write open_orders.local.yaml.",
    )
    promote_orders.add_argument(
        "--raw",
        type=Path,
        default=repo_path("reports", "generated", "account", "open_orders_clob.json"),
        help="Raw orders JSON written by import-clob-orders.",
    )
    promote_orders.add_argument(
        "--output",
        type=Path,
        default=repo_path("context", "open_orders.local.yaml"),
        help=(
            "Where to write real state. Defaults to the gitignored "
            "context/open_orders.local.yaml overlay so live orders never land in "
            "the tracked sample file."
        ),
    )
    promote_orders.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the normalized YAML to stdout instead of writing.",
    )
    promote_orders.set_defaults(func=command_promote_orders)

    paste = subparsers.add_parser(
        "paste-import",
        help=(
            "Validate canonical-shape JSON and write the matching context file. "
            "For users without CLOB auth: paste pre-formatted JSON (e.g. extracted "
            "by an LLM from a screenshot) and promote after schema validation."
        ),
    )
    paste.add_argument(
        "--kind",
        choices=["portfolio", "orders"],
        required=True,
        help="Which canonical file to write to.",
    )
    paste.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to a JSON file matching the canonical Pydantic schema.",
    )
    paste.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output path. Defaults to the gitignored context/portfolio_current.local.yaml "
            "or context/open_orders.local.yaml overlay depending on --kind."
        ),
    )
    paste.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the validated YAML to stdout instead of writing.",
    )
    paste.set_defaults(func=command_paste_import)

    clob_orders = subparsers.add_parser(
        "import-clob-orders",
        help=(
            "Import the wallet's open orders from the Polymarket CLOB via L2 HMAC "
            "auth. Requires POLYMARKET_PROXY_WALLET + POLYMARKET_CLOB_API_KEY + "
            "POLYMARKET_CLOB_SECRET + POLYMARKET_CLOB_PASSPHRASE in the environment."
        ),
    )
    clob_orders.add_argument(
        "--output",
        type=Path,
        default=repo_path("reports", "generated", "account", "open_orders_clob.json"),
    )
    clob_orders.set_defaults(func=command_import_clob_orders)

    clob_balance = subparsers.add_parser(
        "import-clob-balance",
        help=(
            "Import the wallet's COLLATERAL (USDC) balance from the Polymarket "
            "CLOB via L2 HMAC auth. Same credential requirements as "
            "import-clob-orders. Override the proxy type with "
            "POLYMARKET_CLOB_SIGNATURE_TYPE (default 1 = POLY_PROXY)."
        ),
    )
    clob_balance.add_argument(
        "--output",
        type=Path,
        default=repo_path("reports", "generated", "account", "usdc_balance.json"),
    )
    clob_balance.set_defaults(func=command_import_clob_balance)

    promote_balance = subparsers.add_parser(
        "promote-balance",
        help=(
            "Refresh only cash_available in portfolio_current.local.yaml from the "
            "CLOB usdc_balance.json artifact. Positions are preserved."
        ),
    )
    promote_balance.add_argument(
        "--balance",
        type=Path,
        default=repo_path("reports", "generated", "account", "usdc_balance.json"),
        help="Path to the CLOB usdc_balance.json artifact.",
    )
    promote_balance.add_argument(
        "--output",
        type=Path,
        default=repo_path("context", "portfolio_current.local.yaml"),
        help=(
            "Portfolio file to refresh in place. Defaults to the gitignored "
            "context/portfolio_current.local.yaml overlay."
        ),
    )
    promote_balance.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the would-be YAML to stdout instead of writing.",
    )
    promote_balance.set_defaults(func=command_promote_balance)

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

    registry_add = subparsers.add_parser(
        "registry-add",
        help="Add a market to the registry from a Polymarket URL/slug (auto-fills IDs from Gamma).",
    )
    registry_add.add_argument("--url", help="Polymarket event URL.")
    registry_add.add_argument("--slug", help="Event slug (alternative to --url).")
    registry_add.add_argument(
        "--preview",
        action="store_true",
        help="Fetch and print the auto-filled identifiers + suggested judgment "
        "fields as JSON; write nothing.",
    )
    registry_add.add_argument(
        "--all",
        action="store_true",
        dest="add_all",
        help="Add every market/bracket in the event using auto-suggested judgment "
        "fields (skips ones whose suggested market_id already exists).",
    )
    registry_add.add_argument("--market-id", help="Registry market_id ([a-z0-9_]).")
    registry_add.add_argument("--category", default="")
    registry_add.add_argument("--rule-key", default="")
    registry_add.add_argument("--oracle-type", default="")
    registry_add.add_argument("--preferred-side", choices=["YES", "NO"])
    registry_add.add_argument("--thesis-bucket", default="")
    registry_add.add_argument("--notes", default="")
    registry_add.add_argument(
        "--risk-flag",
        action="append",
        dest="risk_flags",
        default=[],
        help="Repeatable risk-flag string.",
    )
    registry_add.add_argument(
        "--rule-risk-json",
        default=None,
        help="JSON object for the rule_risk block (e.g. the suggested one); optional.",
    )
    registry_add.add_argument(
        "--market-index",
        type=int,
        default=0,
        help="Which market within a multi-market event (0-based).",
    )
    registry_add.add_argument("--context-dir", type=Path, default=None)
    registry_add.set_defaults(func=command_registry_add)

    registry_update = subparsers.add_parser(
        "registry-update",
        help="Edit the judgment fields of an existing registry market (IDs stay locked).",
    )
    registry_update.add_argument("--market-id", help="market_id of the entry to edit.")
    registry_update.add_argument(
        "--preview",
        action="store_true",
        help="Print the entry's current editable fields as JSON; write nothing.",
    )
    # Defaults are None so an omitted flag leaves the field unchanged.
    registry_update.add_argument("--name", default=None)
    registry_update.add_argument("--category", default=None)
    registry_update.add_argument("--rule-key", default=None)
    registry_update.add_argument("--oracle-type", default=None)
    registry_update.add_argument("--preferred-side", choices=["YES", "NO"], default=None)
    registry_update.add_argument("--thesis-bucket", default=None)
    registry_update.add_argument("--notes", default=None)
    registry_update.add_argument(
        "--risk-flags",
        dest="risk_flags",
        default=None,
        help="Comma-separated risk flags; replaces the list. Empty string clears it.",
    )
    registry_update.add_argument("--context-dir", type=Path, default=None)
    registry_update.set_defaults(func=command_registry_update)

    registry_delete = subparsers.add_parser(
        "registry-delete",
        help="Remove a market from the registry by market_id.",
    )
    registry_delete.add_argument("--market-id", help="market_id of the entry to remove.")
    registry_delete.add_argument("--context-dir", type=Path, default=None)
    registry_delete.set_defaults(func=command_registry_delete)

    return parser


def command_build_packet(args: argparse.Namespace) -> int:
    path = write_packet(args.output, context_dir=args.context_dir, snapshot_path=args.snapshot)
    print(f"Wrote packet to {path}")
    return 0


def command_packet_build(args: argparse.Namespace) -> int:
    paths = write_model_packets(
        target=args.target,
        output_dir=args.output_dir,
        context_dir=args.context_dir,
        snapshot_path=args.snapshot,
    )
    for path in paths:
        print(f"Wrote {path}")
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
    print(f"Wrote ledger-ready ticket to {path.with_suffix('.json')}")
    return 0


def command_import_public_positions(args: argparse.Namespace) -> int:
    try:
        path = write_public_positions(args.address, args.output)
    except AccountImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Wrote public positions import to {path}")
    if not args.skip_balance:
        try:
            creds = load_clob_credentials_from_env()
        except AccountImportError as exc:
            # Cash needs CLOB auth; on-chain balance at the proxy is structurally
            # always zero. Skip rather than write a misleading $0 artifact.
            print(
                f"USDC balance fetch skipped (no CLOB credentials): {exc}",
                file=sys.stderr,
            )
        else:
            try:
                balance_path = write_clob_balance(creds, args.balance_output)
                print(f"Wrote CLOB collateral balance to {balance_path}")
            except AccountImportError as exc:
                print(f"USDC balance fetch failed (non-fatal): {exc}", file=sys.stderr)
    return 0


def command_import_clob_balance(args: argparse.Namespace) -> int:
    try:
        creds = load_clob_credentials_from_env()
        path = write_clob_balance(creds, args.output)
    except AccountImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Wrote CLOB collateral balance to {path}")
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
        read_usdc_balance,
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
    cash_source = "--cash override"
    if cash is None:
        balance = read_usdc_balance(args.balance)
        if balance is not None:
            cash = balance
            cash_source = f"CLOB collateral ({args.balance.name})"
    if cash is None:
        try:
            live = load_live_state()
            cash = float(live.account_snapshot.cash_available)
            cash_source = "live_state.yaml"
        except Exception as exc:
            print(f"Could not read cash_available from live_state.yaml: {exc}", file=sys.stderr)
            return 1
    print(f"cash_available source: {cash_source} (${cash:.2f})", file=sys.stderr)

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
        if len(portfolio.positions) == 0:
            print(
                f"WARNING: all {len(skipped)} imported positions were skipped — "
                f"{args.output} was overwritten with an empty positions list. "
                f"Add the missing condition_id values to context/market_registry.yaml "
                f"and re-run promote-positions.",
                file=sys.stderr,
            )
    return 0


def command_promote_balance(args: argparse.Namespace) -> int:
    from polyberg.account_normalizer import _dump_portfolio_yaml, promote_balance

    try:
        updated, previous_cash = promote_balance(args.balance, args.output)
    except NormalizerError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    yaml_text = _dump_portfolio_yaml(updated)
    print(
        f"cash_available: ${previous_cash:.2f} → ${updated.cash_available:.2f} "
        f"(source: {args.balance.name})",
        file=sys.stderr,
    )
    if args.dry_run:
        sys.stdout.write(yaml_text)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml_text, encoding="utf-8")
    print(f"Wrote refreshed cash to {args.output}")
    return 0


def command_promote_orders(args: argparse.Namespace) -> int:
    import json as _json

    from polyberg.account_normalizer import (
        _dump_open_orders_yaml,
        normalize_clob_open_orders,
    )
    from polyberg.loaders import load_market_registry

    if not args.raw.exists():
        print(f"Raw orders file not found: {args.raw}", file=sys.stderr)
        return 1
    try:
        raw_doc = _json.loads(args.raw.read_text(encoding="utf-8"))
    except _json.JSONDecodeError as exc:
        print(f"Invalid JSON in {args.raw}: {exc}", file=sys.stderr)
        return 1
    payload = raw_doc.get("payload", raw_doc) if isinstance(raw_doc, dict) else raw_doc

    try:
        registry = load_market_registry()
        open_orders, skipped = normalize_clob_open_orders(payload, registry)
    except NormalizerError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    yaml_text = _dump_open_orders_yaml(open_orders)
    if args.dry_run:
        sys.stdout.write(yaml_text)
        if skipped:
            print(f"\n# skipped: {len(skipped)}", file=sys.stderr)
            for s in skipped:
                print(f"#   {s}", file=sys.stderr)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml_text, encoding="utf-8")
    print(f"Wrote canonical open orders to {args.output}")
    total = len(open_orders.buy_orders) + len(open_orders.sell_orders)
    if skipped:
        print(f"Skipped {len(skipped)} orders (not in registry):", file=sys.stderr)
        for s in skipped:
            print(f"  - {s}", file=sys.stderr)
        if total == 0:
            print(
                f"WARNING: all {len(skipped)} imported orders were skipped — "
                f"{args.output} was overwritten with empty buy/sell lists. "
                f"Add the missing condition_id values to context/market_registry.yaml "
                f"and re-run promote-orders.",
                file=sys.stderr,
            )
    return 0


def command_paste_import(args: argparse.Namespace) -> int:
    if not args.input.exists():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1
    raw_text = args.input.read_text(encoding="utf-8")

    default_output = {
        "portfolio": repo_path("context", "portfolio_current.local.yaml"),
        "orders": repo_path("context", "open_orders.local.yaml"),
    }
    output = args.output or default_output[args.kind]

    try:
        yaml_text = import_paste(
            kind=args.kind,
            raw_text=raw_text,
            output_path=output,
            dry_run=args.dry_run,
            portfolio_path_for_thesis=default_output["portfolio"]
            if args.kind == "portfolio"
            else None,
        )
    except PasteImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.dry_run:
        sys.stdout.write(yaml_text)
        return 0
    print(f"Wrote {args.kind} to {output}")
    return 0


def command_import_clob_orders(args: argparse.Namespace) -> int:
    try:
        creds = load_clob_credentials_from_env()
        path = write_clob_open_orders(creds, args.output)
    except AccountImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Wrote CLOB open orders to {path}")
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


def _load_registry_for_suggest(path: Path):
    import yaml as _yaml

    from polyberg.models import MarketRegistry

    return MarketRegistry(**(_yaml.safe_load(path.read_text(encoding="utf-8")) or {}))


def command_registry_add(args: argparse.Namespace) -> int:
    import json as _json

    from polyberg.registry_editor import (
        RegistryEditError,
        build_market,
        fetch_candidate,
        market_display_name,
        registry_path,
        select_market,
        suggest_market_id,
        upsert_market_entry,
    )
    from polyberg.registry_suggest import suggest_for_market

    source = args.url or args.slug
    if not source:
        print("Provide --url or --slug", file=sys.stderr)
        return 1
    try:
        candidate = fetch_candidate(source)
    except RegistryEditError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    target = registry_path(args.context_dir)
    registry = _load_registry_for_suggest(target)
    existing_cids = {m.condition_id for m in registry.markets if m.condition_id}

    if args.preview:
        try:
            market = select_market(candidate, args.market_index)
        except RegistryEditError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        per_market = [suggest_for_market(candidate, m, registry) for m in candidate["markets"]]
        payload = {
            "name": candidate["name"],
            "polymarket_url": candidate["polymarket_url"],
            "event_slug": candidate["event_slug"],
            "resolution_source": candidate["resolution_source"],
            "tags": candidate["tags"],
            "suggested_market_id": suggest_market_id(market_display_name(candidate, market)),
            "num_markets": len(candidate["markets"]),
            "market_index": args.market_index,
            "condition_id": market["condition_id"],
            "yes_token_id": market["yes_token_id"],
            "no_token_id": market["no_token_id"],
            "outcomes": market["outcomes"],
            "resolution_date": market["resolution_date"],
            "description": market["description"],
            "group_item_title": market["group_item_title"],
            # Suggested judgment fields for the selected market (prefills the form).
            "suggestion": per_market[args.market_index],
            "markets": [
                {
                    "index": i,
                    "question": m["question"],
                    "condition_id": m["condition_id"],
                    "group_item_title": m["group_item_title"],
                    "suggested_market_id": per_market[i]["market_id"],
                    "preferred_side": per_market[i]["preferred_side"],
                    "matched_market_id": per_market[i]["matched_market_id"],
                    # Already in the registry by id, OR the same on-chain market
                    # (condition_id) under a different id — either way, don't re-add.
                    "exists": (
                        per_market[i]["market_id"] in registry.market_ids
                        or m["condition_id"] in existing_cids
                    ),
                }
                for i, m in enumerate(candidate["markets"])
            ],
        }
        print(_json.dumps(payload, indent=2))
        return 0

    if args.add_all:
        return _registry_add_all(candidate, registry, target)

    missing = [
        name
        for name, val in (
            ("--market-id", args.market_id),
            ("--category", args.category),
            ("--rule-key", args.rule_key),
            ("--oracle-type", args.oracle_type),
            ("--preferred-side", args.preferred_side),
        )
        if not val
    ]
    if missing:
        print(f"Missing required fields for commit: {', '.join(missing)}", file=sys.stderr)
        return 1

    rule_risk = None
    if args.rule_risk_json:
        try:
            rule_risk = _json.loads(args.rule_risk_json)
        except _json.JSONDecodeError as exc:
            print(f"Invalid --rule-risk-json: {exc}", file=sys.stderr)
            return 1

    try:
        entry = build_market(
            candidate,
            market_id=args.market_id,
            category=args.category,
            rule_key=args.rule_key,
            oracle_type=args.oracle_type,
            preferred_side=args.preferred_side,
            thesis_bucket=args.thesis_bucket,
            notes=args.notes,
            risk_flags=args.risk_flags,
            rule_risk=rule_risk,
            market_index=args.market_index,
        )
        path = upsert_market_entry(entry, target)
    except RegistryEditError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # pydantic ValidationError, bad market_id, etc.
        print(f"Could not build registry entry: {exc}", file=sys.stderr)
        return 1
    print(f"Added market {entry.market_id} to {path}")
    return 0


def _registry_add_all(candidate: dict, registry, target: Path) -> int:
    """Add every market/bracket in an event using auto-suggested judgment fields.

    Each bracket is suggested independently (so a band inherits its family's
    rule_key/oracle but keeps a safe default side). Brackets whose suggested
    market_id already exists are skipped, not overwritten. Prints a JSON summary
    so the GUI can report what landed.
    """
    import json as _json

    from polyberg.registry_editor import (
        RegistryEditError,
        build_market,
        upsert_market_entry,
    )
    from polyberg.registry_suggest import suggest_for_market

    added: list[str] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    for idx, market in enumerate(candidate["markets"]):
        sug = suggest_for_market(candidate, market, registry)
        mid = sug["market_id"]
        existing_cids = {m.condition_id for m in registry.markets if m.condition_id}
        if mid in registry.market_ids:
            skipped.append({"market_id": mid, "reason": "already exists"})
            continue
        if market["condition_id"] and market["condition_id"] in existing_cids:
            skipped.append({"market_id": mid, "reason": "condition_id already in registry"})
            continue
        try:
            entry = build_market(
                candidate,
                market_id=mid,
                category=sug["category"],
                rule_key=sug["rule_key"],
                oracle_type=sug["oracle_type"],
                preferred_side=sug["preferred_side"],
                thesis_bucket=sug["thesis_bucket"],
                notes=sug["notes"],
                risk_flags=sug["risk_flags"],
                rule_risk=sug["rule_risk"],
                market_index=idx,
            )
            upsert_market_entry(entry, target)
            # Refresh so the next bracket's duplicate check sees what just landed.
            registry = _load_registry_for_suggest(target)
            added.append(mid)
        except (RegistryEditError, Exception) as exc:  # noqa: BLE001 - report, keep going
            failed.append({"market_id": mid, "error": str(exc)})
    print(
        _json.dumps(
            {"added": added, "skipped": skipped, "failed": failed, "path": str(target)},
            indent=2,
        )
    )
    return 0 if not failed else 1


def command_registry_update(args: argparse.Namespace) -> int:
    import json as _json

    from polyberg.registry_editor import (
        RegistryEditError,
        get_editable_fields,
        registry_path,
        update_market_entry,
    )

    if not args.market_id:
        print("Provide --market-id", file=sys.stderr)
        return 1
    path = registry_path(args.context_dir)

    if args.preview:
        try:
            fields = get_editable_fields(args.market_id, path)
        except RegistryEditError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(_json.dumps(fields, indent=2, default=str))
        return 0

    # Only flags that were actually passed become edits; None means "leave as-is".
    updates: dict[str, object] = {}
    for flag, value in (
        ("name", args.name),
        ("category", args.category),
        ("thesis_bucket", args.thesis_bucket),
        ("rule_key", args.rule_key),
        ("oracle_type", args.oracle_type),
        ("preferred_side", args.preferred_side),
        ("notes", args.notes),
    ):
        if value is not None:
            updates[flag] = value
    # --risk-flags is a comma string so "" can clear the list; None leaves it.
    if args.risk_flags is not None:
        updates["risk_flags"] = [f.strip() for f in args.risk_flags.split(",") if f.strip()]

    if not updates:
        print("No fields to update (pass at least one editable field)", file=sys.stderr)
        return 1

    try:
        out = update_market_entry(args.market_id, updates, path)
    except RegistryEditError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # pydantic ValidationError, etc.
        print(f"Could not update registry entry: {exc}", file=sys.stderr)
        return 1
    print(f"Updated market {args.market_id} in {out}")
    return 0


def command_registry_delete(args: argparse.Namespace) -> int:
    from polyberg.registry_editor import (
        RegistryEditError,
        delete_market_entry,
        registry_path,
    )

    if not args.market_id:
        print("Provide --market-id", file=sys.stderr)
        return 1
    try:
        out = delete_market_entry(args.market_id, registry_path(args.context_dir))
    except RegistryEditError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Deleted market {args.market_id} from {out}")
    return 0


def _build_ladder_plan_from_args(args: argparse.Namespace):
    """Shared plan construction for `ladder plan` and `ladder execute`.

    Returns (exit_code, plan, url_map); plan/url_map are None unless exit_code is 0.
    """
    import json as _json
    from decimal import Decimal

    from polyberg.ladder.diff import diff_ladders
    from polyberg.ladder.live_orders import live_rungs_from_raw
    from polyberg.ladder.models import load_target_ladders
    from polyberg.ladder.validate import LadderValidationError, validate_targets
    from polyberg.loaders import LoaderError, load_market_registry, load_portfolio

    try:
        registry = load_market_registry()
    except LoaderError as exc:
        print(str(exc), file=sys.stderr)
        return 1, None, None

    try:
        targets = load_target_ladders(args.target, registry)
    except LoaderError as exc:
        print(str(exc), file=sys.stderr)
        return 1, None, None

    # Resolve cash: --cash flag > live CLOB fetch > portfolio yaml (+stale warn)
    cash: Decimal | None = None
    cash_is_stale = False
    if args.cash is not None:
        cash = Decimal(str(args.cash))
    else:
        try:
            from polyberg.collectors.polymarket_clob_auth import load_clob_credentials_from_env
            from polyberg.collectors.polymarket_clob_balance import (
                balance_to_decimal_usdc,
                fetch_collateral_balance,
            )
            creds = load_clob_credentials_from_env()
            raw_balance = fetch_collateral_balance(creds)
            cash = balance_to_decimal_usdc(raw_balance["balance"])
        except Exception:  # noqa: BLE001 - missing creds or network; fall through
            pass
    if cash is None:
        try:
            portfolio = load_portfolio()
            cash = Decimal(str(portfolio.cash_available))
            cash_is_stale = True
        except LoaderError as exc:
            print(f"Cannot resolve cash_available: {exc}", file=sys.stderr)
            return 1, None, None

    # Resolve live orders: --live-from file or live CLOB fetch
    if args.live_from is not None:
        if not args.live_from.exists():
            print(f"--live-from file not found: {args.live_from}", file=sys.stderr)
            return 1, None, None
        try:
            raw_doc = _json.loads(args.live_from.read_text(encoding="utf-8"))
        except _json.JSONDecodeError as exc:
            print(f"Invalid JSON in {args.live_from}: {exc}", file=sys.stderr)
            return 1, None, None
        raw_orders = raw_doc.get("payload", raw_doc) if isinstance(raw_doc, dict) else raw_doc
        if not isinstance(raw_orders, list):
            print(f"Expected list of orders in {args.live_from}", file=sys.stderr)
            return 1, None, None
    else:
        try:
            from polyberg.collectors.polymarket_clob_orders import fetch_open_orders
            creds = load_clob_credentials_from_env()
            raw_orders = fetch_open_orders(creds)
        except AccountImportError as exc:
            print(str(exc), file=sys.stderr)
            return 1, None, None

    try:
        live_rungs, unmapped = live_rungs_from_raw(raw_orders, registry)
    except ValueError as exc:
        print(f"Live orders error: {exc}", file=sys.stderr)
        return 1, None, None

    # Validate targets before diff
    try:
        warnings = validate_targets(targets, registry, cash, cash_is_stale)
    except LadderValidationError as exc:
        for msg in exc.messages:
            print(f"[hard fail] {msg}", file=sys.stderr)
        return 2, None, None

    # Build matching config with any CLI overrides
    matching = targets.matching
    overrides: dict[str, float] = {}
    if args.price_tolerance is not None:
        overrides["price_tolerance"] = args.price_tolerance
    if args.shares_tolerance is not None:
        overrides["shares_tolerance"] = args.shares_tolerance
    if overrides:
        matching = matching.model_copy(update=overrides)

    plan = diff_ladders(
        targets,
        live_rungs,
        unmapped,
        matching=matching,
        manage_all=args.manage_all,
    )
    if warnings:
        plan.warnings.extend(warnings)

    url_map = {m.market_id: m.polymarket_url for m in registry.markets}
    return 0, plan, url_map


def command_ladder_plan(args: argparse.Namespace) -> int:
    import json as _json

    from polyberg.ladder.render import plan_to_dict, render_plan

    as_json = getattr(args, "as_json", False)
    rc, plan, url_map = _build_ladder_plan_from_args(args)
    if rc != 0:
        if as_json and rc == 2:
            # Hard validation failure: emit a structured error the GUI can render
            # as a red banner instead of a (missing) plan. Messages were already
            # printed to stderr by _build_ladder_plan_from_args.
            print(_json.dumps({"ok": False, "exit_code": 2}))
        return rc
    if as_json:
        print(_json.dumps({"ok": True, "plan": plan_to_dict(plan, url_map)}))
        return 0
    output = render_plan(plan, url_map=url_map, paste=not args.no_paste)
    print(output, end="")
    return 0


def command_ladder_execute(args: argparse.Namespace) -> int:
    from polyberg.ladder.executor import execute_plan
    from polyberg.ladder.render import render_plan

    rc, plan, url_map = _build_ladder_plan_from_args(args)
    if rc != 0:
        return rc

    print(render_plan(plan, url_map=url_map, paste=False), end="")

    if not plan.cancel and not plan.place:
        print("Nothing to execute: plan has no cancels or placements.")
        return 0

    try:
        creds = load_clob_credentials_from_env()
    except AccountImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    log_path = args.log if args.log is not None else repo_path("live", "order_log.jsonl")
    return execute_plan(plan, creds, log_path, url_map=url_map)


def command_ladder_cancel(args: argparse.Namespace) -> int:
    """Cancel one order by id over the API and append a log entry. The GUI's
    confirm modal is the human gate; this command never prompts."""
    import json as _json
    from datetime import datetime

    from polyberg.config import get_timezone
    from polyberg.ladder.clob_cancel import ClobCancelError, cancel_order
    from polyberg.ladder.executor import _log_entry, append_order_log

    try:
        creds = load_clob_credentials_from_env()
    except AccountImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    log_path = args.log if args.log is not None else repo_path("live", "order_log.jsonl")
    ts = datetime.now(get_timezone())
    try:
        response = cancel_order(creds, args.order_id)
    except ClobCancelError as exc:
        append_order_log(
            log_path,
            _log_entry(
                ts, "CANCEL", "", "", "", 0.0, 0.0, args.order_id, "http_error",
                exc.excerpt or str(exc),
            ),
        )
        print(f"Cancel failed for {args.order_id}: {exc}", file=sys.stderr)
        return 1
    append_order_log(
        log_path,
        _log_entry(
            ts, "CANCEL", "", "", "", 0.0, 0.0, args.order_id, "ok", _json.dumps(response)
        ),
    )
    print(f"Cancelled {args.order_id}")
    return 0


def command_ladder_preflight(args: argparse.Namespace) -> int:
    """Fire GET /balance-allowance/update (required after closes before placing)."""
    import json as _json

    from polyberg.ladder.executor import fire_preflight

    try:
        creds = load_clob_credentials_from_env()
    except AccountImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        response = fire_preflight(creds)
    except AccountImportError as exc:
        print(f"Pre-flight failed: {exc}", file=sys.stderr)
        return 1
    print(_json.dumps(response))
    return 0


def command_ladder_record_manual(args: argparse.Namespace) -> int:
    """Append a manual_confirmed PLACE entry (GUI marks a placement done)."""
    from polyberg.ladder.executor import record_manual_placement

    log_path = args.log if args.log is not None else repo_path("live", "order_log.jsonl")
    record_manual_placement(
        log_path,
        args.market_id,
        args.outcome,
        args.side,
        args.price,
        args.shares,
    )
    print(
        f"Recorded manual PLACE {args.market_id} {args.outcome} {args.side} "
        f"@ {args.price:.4f} x {args.shares:.1f}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    load_repo_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
