"""Command-line interface: scan, plan, apply."""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from collections.abc import Callable, Sequence

from tidymind import __version__
from tidymind.errors import (
    EXIT_CANCELLED,
    EXIT_INCOMPLETE,
    EXIT_INTERNAL,
    EXIT_OK,
    TidyMindError,
)
from tidymind.executor import Status, execute
from tidymind.model_client import DEFAULT_ENDPOINT, DEFAULT_MODEL, OllamaClient
from tidymind.planner import build_plan, load_plan, write_plan
from tidymind.reporter import count_outcomes, render_results, render_scan
from tidymind.reviewer import confirm, render_preview
from tidymind.scanner import resolve_root, scan
from tidymind.validator import validate_plan

ENDPOINT_ENV = "TIDYMIND_OLLAMA_URL"

EPILOG = """\
exit codes:
  0 success      1 internal error      2 usage/configuration error
  3 input error  4 model unavailable   5 invalid plan or root mismatch
  6 not approved (nothing changed)     7 some operations skipped or failed

examples:
  tidymind scan ~/Downloads
  tidymind plan ~/Downloads --output plan.json
  tidymind apply plan.json
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tidymind",
        description=(
            "Organize a folder with a local AI model. The model only proposes; "
            "you review the full plan and approve before anything moves."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"tidymind {__version__}")
    parser.add_argument("--debug", action="store_true", help="show full tracebacks")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="list eligible files (changes nothing)")
    p_scan.add_argument("directory")

    p_plan = sub.add_parser("plan", help="ask the local model for a plan and preview it")
    p_plan.add_argument("directory")
    p_plan.add_argument("--output", "-o", help="write the plan JSON here (never overwrites)")
    p_plan.add_argument(
        "--dry-run", action="store_true", help="preview only; do not write any file"
    )
    p_plan.add_argument("--model", default=DEFAULT_MODEL)
    p_plan.add_argument(
        "--endpoint",
        default=None,
        help=f"loopback Ollama URL (default {DEFAULT_ENDPOINT}, or ${ENDPOINT_ENV})",
    )
    p_plan.add_argument("--timeout", type=float, default=120.0, help="seconds per request")

    p_apply = sub.add_parser("apply", help="validate, preview and (after approval) apply a plan")
    p_apply.add_argument("plan")
    p_apply.add_argument("--root", help="assert the directory the plan must belong to")
    p_apply.add_argument(
        "--dry-run", action="store_true", help="validate and preview only; ask nothing, change nothing"
    )
    return parser


def _cmd_scan(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    out(render_scan(scan(args.directory)))
    return EXIT_OK


def _cmd_plan(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    result = scan(args.directory)
    out(render_scan(result))
    if not result.eligible:
        out("\nNothing to organize.")
        return EXIT_OK
    endpoint = args.endpoint or os.environ.get(ENDPOINT_ENV) or DEFAULT_ENDPOINT
    client = OllamaClient(endpoint=endpoint, model=args.model, timeout=args.timeout)
    out(f"\nAsking local model '{args.model}' (metadata stays on this machine)...")
    plan = build_plan(result, client.suggest(result.eligible))
    report = validate_plan(plan)
    out("\n" + render_preview(report))
    if args.output and args.dry_run:
        out(f"\nDry run: plan NOT written to {args.output}.")
    elif args.output:
        write_plan(plan, args.output)
        out(f"\nPlan written to {args.output}. Review it, then run: tidymind apply {args.output}")
    elif not args.dry_run:
        out("\nNo --output given, so no plan was saved and nothing was changed.")
    return EXIT_OK


def _cmd_apply(
    args: argparse.Namespace, out: Callable[[str], None], ask: Callable[[str], str]
) -> int:
    plan = load_plan(args.plan)
    expected = resolve_root(args.root) if args.root else None
    report = validate_plan(plan, expected)  # re-validate: a saved plan is never trusted
    out(render_preview(report))
    if args.dry_run:
        out("\nDry run: nothing was changed.")
        return EXIT_OK
    if not report.operations:
        out("\nNo safe operations to apply.")
        return EXIT_INCOMPLETE if report.unsafe else EXIT_OK
    if not confirm(len(report.operations), report.root, ask):
        out("\nNot approved. Nothing was changed.")
        return EXIT_CANCELLED
    outcomes = execute(report)
    out("\n" + render_results(outcomes))
    counts = count_outcomes(outcomes)
    return EXIT_INCOMPLETE if counts[Status.SKIPPED] or counts[Status.FAILED] else EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    out: Callable[[str], None] = print,
    ask: Callable[[str], str] = input,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan":
            return _cmd_scan(args, out)
        if args.command == "plan":
            return _cmd_plan(args, out)
        return _cmd_apply(args, out, ask)
    except TidyMindError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return exc.exit_code
    except Exception as exc:
        print(f"Unexpected error: {type(exc).__name__}. Re-run with --debug for details.", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return EXIT_INTERNAL

