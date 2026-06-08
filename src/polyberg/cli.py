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


def main(argv: list[str] | None = None) -> int:
    load_repo_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
