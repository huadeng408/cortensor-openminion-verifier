"""Command-line entrypoint for Cortensor OpenMinion Verifier."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from openminion.api import AgentOutputValidationError, ProviderError

from cortensor_verifier.auditor import ConsensusAuditor
from cortensor_verifier.probe import (
    BuildingBlockProbeRunner,
    assert_no_plaintext_secrets,
    export_probe_docs,
)
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
    pass_mode = audit_parser.add_mutually_exclusive_group()
    pass_mode.add_argument(
        "--single-pass",
        dest="single_pass",
        action="store_true",
        default=True,
        help="Execute single-pass structured audit (default).",
    )
    pass_mode.add_argument(
        "--multi-pass",
        dest="single_pass",
        action="store_false",
        help="Execute dual-perspective corroborator/skeptic subagent consensus audit.",
    )
    audit_parser.add_argument(
        "--session-id",
        default=None,
        help="Session identifier for multi-turn continuity and isolated MemoryBundle.",
    )
    audit_parser.add_argument(
        "--publish",
        action="store_true",
        default=False,
        help="Route verified ConsensusVerdict through approval-gated Handoff publication.",
    )
    audit_parser.add_argument(
        "--approval-mode",
        choices=("allow_once", "deny", "pause"),
        default=None,
        help="Policy confirmation mode for --publish (defaults fail-closed to pause).",
    )
    audit_parser.add_argument(
        "--resume-thread-id",
        default=None,
        help="Paused publication thread_id to resume with --approval-mode.",
    )
    audit_parser.add_argument(
        "--approval-id",
        default=None,
        help="Optional explicit authorization identifier for allow_once replay checks.",
    )
    audit_parser.add_argument(
        "--publication-log",
        default=None,
        help="Optional JSONL path for published verdicts (defaults under data_root).",
    )
    audit_parser.add_argument(
        "--memory-bundle-out",
        default=None,
        help="Optional file path to export the session MemoryBundle JSON.",
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

    probe_parser = subparsers.add_parser(
        "probe",
        help="Run all 10 OpenMinion 0.1 building-block probes and optionally export docs.",
    )
    probe_parser.add_argument(
        "--preset",
        choices=PROVIDER_PRESETS,
        default="openai-compatible",
        help="Provider runtime preset.",
    )
    probe_parser.add_argument("--base-url", help="Override provider base URL.")
    probe_parser.add_argument("--model", help="Override model name.")
    probe_parser.add_argument(
        "--api-key-env",
        help="Environment variable name holding the provider API key.",
    )
    probe_parser.add_argument(
        "--home-root",
        help="Isolated home directory for .openminion/agents.json.",
    )
    probe_parser.add_argument(
        "--data-root",
        help="Isolated state root directory (.openminion-state).",
    )
    probe_parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Maximum provider retry attempts per turn.",
    )
    probe_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=15,
        help="Provider HTTP timeout in seconds.",
    )
    probe_parser.add_argument(
        "--probes",
        nargs="+",
        help="Optional subset of building-block probe IDs to execute (default: all 10).",
    )
    probe_parser.add_argument(
        "--export-docs",
        action="store_true",
        default=False,
        help="Write sanitized BUILDING_BLOCKS_TESTED.md and WHAT_WE_LEARNED.md.",
    )
    probe_parser.add_argument(
        "--docs-dir",
        default="docs",
        help="Target directory for --export-docs output (default: docs).",
    )
    probe_parser.add_argument(
        "-o",
        "--output",
        help="Optional file path to write the ProbeSuiteReport JSON.",
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
        bundle = auditor.audit_claim(
            dossier,
            single_pass=bool(args.single_pass),
            session_id=args.session_id,
            thread_id=args.resume_thread_id,
            publish=bool(args.publish),
            approval_mode=args.approval_mode,
            approval_id=args.approval_id,
            publication_log_path=args.publication_log,
            memory_bundle_out=args.memory_bundle_out,
        )

    rendered = bundle.model_dump_json(indent=2)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def _run_probe(args: argparse.Namespace) -> int:
    runner = BuildingBlockProbeRunner(
        preset=args.preset,
        base_url=args.base_url,
        model=args.model,
        api_key_env=args.api_key_env,
        home_root=args.home_root,
        data_root=args.data_root,
        provider_retry_max_attempts=args.max_retries,
        timeout_seconds=args.timeout_seconds,
        probe_ids=args.probes,
    )
    report = runner.run_all()
    if args.export_docs:
        export_probe_docs(
            report,
            docs_dir=args.docs_dir,
            secret_env_names=[args.api_key_env] if args.api_key_env else None,
        )

    rendered = report.model_dump_json(indent=2)
    assert_no_plaintext_secrets(
        rendered,
        secret_env_names=[args.api_key_env] if args.api_key_env else None,
    )
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.all_passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint returning process exit status."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "audit":
            return _run_audit(args)
        if args.command == "probe":
            return _run_probe(args)
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
