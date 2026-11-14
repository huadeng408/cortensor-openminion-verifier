"""Command-line entrypoint for Cortensor OpenMinion Verifier."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from openminion.api import AgentOutputValidationError, ProviderError

from cortensor_verifier.auditor import ConsensusAuditor
from cortensor_verifier.runtime_factory import PROVIDER_PRESETS
from cortensor_verifier.tools import load_claim_dossier, load_dossier_from_file


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="cortensor-verifier",
        description="Isolated OpenMinion + Cortensor consensus verifier CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser(
        "audit",
        help="Audit a claim dossier via isolated openminion runtime.",
    )
    claim_group = audit_parser.add_mutually_exclusive_group(required=True)
    claim_group.add_argument(
        "--claim-id",
        help="Claim identifier to load from fixtures/claim_dossiers.json.",
    )
    claim_group.add_argument(
        "--dossier",
        help="Path to a standalone ClaimDossier JSON file.",
    )
    audit_parser.add_argument(
        "--fixtures",
        help="Optional fixture catalog JSON path when using --claim-id.",
    )
    audit_parser.add_argument(
        "--preset",
        choices=PROVIDER_PRESETS,
        default="openai-compatible",
        help="Provider runtime preset.",
    )
    audit_parser.add_argument("--base-url", help="Override provider base URL.")
    audit_parser.add_argument("--model", help="Override model name.")
    audit_parser.add_argument(
        "--api-key-env",
        help="Environment variable name holding the provider API key.",
    )
    audit_parser.add_argument(
        "--home-root",
        help="Isolated home directory for .openminion/agents.json.",
    )
    audit_parser.add_argument(
        "--data-root",
        help="Isolated state root directory (.openminion-state).",
    )
    audit_parser.add_argument(
        "--single-pass",
        action="store_true",
        default=True,
        help="Execute single-pass structured audit (default in C1).",
    )
    audit_parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Maximum provider retry attempts per turn.",
    )
    audit_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=None,
        help="Provider HTTP timeout in seconds.",
    )
    audit_parser.add_argument(
        "-o",
        "--output",
        help="Optional file path to write the AuditRunBundle JSON.",
    )
    return parser


def _run_audit(args: argparse.Namespace) -> int:
    if args.claim_id:
        dossier = load_claim_dossier(args.claim_id, fixture_path=args.fixtures)
    else:
        dossier = load_dossier_from_file(args.dossier)

    with ConsensusAuditor(
        preset=args.preset,
        base_url=args.base_url,
        model=args.model,
        api_key_env=args.api_key_env,
        home_root=args.home_root,
        data_root=args.data_root,
        provider_retry_max_attempts=args.max_retries,
        timeout_seconds=args.timeout_seconds,
    ) as auditor:
        bundle = auditor.audit_claim(dossier, single_pass=bool(args.single_pass))

    rendered = bundle.model_dump_json(indent=2)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint returning process exit status."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "audit":
            return _run_audit(args)
        parser.error(f"Unsupported command: {args.command}")
    except (
        AgentOutputValidationError,
        ProviderError,
        KeyError,
        FileNotFoundError,
        ValueError,
    ) as exc:
        print(f"error ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
