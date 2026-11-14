"""Single-pass and claim-level ConsensusAuditor driving real openminion Agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Sequence

from openminion.api import APIRuntime, Agent, AgentRunResult

from cortensor_verifier.models import (
    AuditRunBundle,
    ClaimDossier,
    ConsensusVerdict,
    VerifierPassResult,
)
from cortensor_verifier.runtime_factory import create_isolated_runtime
from cortensor_verifier.tools import READ_ONLY_VERIFIER_TOOLS, assert_read_only_tools


class ConsensusAuditor:
    """Orchestrates evidence-backed verification passes using isolated openminion runtimes."""

    def __init__(
        self,
        *,
        runtime: APIRuntime | None = None,
        preset: str = "openai-compatible",
        base_url: str | None = None,
        model: str | None = None,
        api_key_env: str | None = None,
        agent_id: str = "verifier",
        home_root: str | Path | None = None,
        data_root: str | Path | None = None,
        config_path: str | Path | None = None,
        tools: Sequence[Any] | None = None,
        tool_call_strategy: Literal["native", "hybrid"] = "native",
        timeout_seconds: int | None = None,
        provider_retry_max_attempts: int = 2,
        http_connection_reuse_enabled: bool = False,
        cortensor_api_mode: str = "auto",
        cortensor_session_id: int = 1,
    ) -> None:
        self.tools = assert_read_only_tools(
            READ_ONLY_VERIFIER_TOOLS if tools is None else tools
        )
        self._allowed_tool_names = {item.tool_decl.name for item in self.tools}
        self._runtime = runtime
        self._owns_runtime = runtime is None
        self.preset = preset
        self.base_url = base_url
        self.model = model
        self.api_key_env = api_key_env
        self.agent_id = agent_id
        self.home_root = home_root
        self.data_root = data_root
        self.config_path = config_path
        self.tool_call_strategy = tool_call_strategy
        self.timeout_seconds = timeout_seconds
        self.provider_retry_max_attempts = provider_retry_max_attempts
        self.http_connection_reuse_enabled = http_connection_reuse_enabled
        self.cortensor_api_mode = cortensor_api_mode
        self.cortensor_session_id = cortensor_session_id

    def __enter__(self) -> "ConsensusAuditor":
        self._ensure_runtime()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_runtime and self._runtime is not None:
            self._runtime.close()
            self._runtime = None

    def _ensure_runtime(self) -> APIRuntime:
        if self._runtime is None:
            self._runtime = create_isolated_runtime(
                preset=self.preset,
                base_url=self.base_url,
                model=self.model,
                api_key_env=self.api_key_env,
                agent_id=self.agent_id,
                home_root=self.home_root,
                data_root=self.data_root,
                config_path=self.config_path,
                tool_call_strategy=self.tool_call_strategy,
                timeout_seconds=self.timeout_seconds,
                provider_retry_max_attempts=self.provider_retry_max_attempts,
                http_connection_reuse_enabled=self.http_connection_reuse_enabled,
                cortensor_api_mode=self.cortensor_api_mode,
                cortensor_session_id=self.cortensor_session_id,
            )
            self._owns_runtime = True
        return self._runtime

    def _read_only_approval_guard(
        self,
        tool_name: str,
        args: dict[str, Any],
        approval_id: str,
    ) -> bool:
        del args, approval_id
        return tool_name in self._allowed_tool_names

    def _build_instructions(self, pass_role: str) -> str:
        return (
            f"You are performing a '{pass_role}' evidence verification pass for a Claim Dossier. "
            "Use the provided READ_ONLY evidence tools to gather and verify sources, then respond "
            "with ONLY valid JSON matching the VerifierPassResult schema: "
            "{verdict: 'SUPPORTED'|'REFUTED'|'INCONCLUSIVE', confidence: float in [0,1], "
            "rationale: str, citations: [{source_id, title, url, excerpt, published_at}], "
            f"pass_role: '{pass_role}'}}."
        )

    def _build_prompt(self, dossier: ClaimDossier, pass_role: str) -> str:
        serialized = json.dumps(dossier.model_dump(mode="json"), indent=2, sort_keys=True)
        return (
            f"Audit the following Claim Dossier as the '{pass_role}' verifier pass.\n"
            "Inspect public evidence using the read-only tools before issuing your structured JSON verdict.\n\n"
            f"Claim Dossier:\n{serialized}"
        )

    def _extract_tool_calls(self, result: AgentRunResult[VerifierPassResult]) -> list[str]:
        collected: list[str] = []
        raw_meta = result.raw.get("metadata")
        meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        candidates: list[Any] = [
            result.metadata.get("tool_calls_cumulative"),
            result.metadata.get("tool_results"),
            result.metadata.get("tool_calls"),
            result.metadata.get("tools_used"),
            meta.get("tool_calls_cumulative"),
            meta.get("tool_results"),
            meta.get("tool_calls"),
            meta.get("tools_used"),
        ]

        for entry in candidates:
            if isinstance(entry, str) and entry.strip().startswith("["):
                try:
                    entry = json.loads(entry)
                except json.JSONDecodeError:
                    continue
            if not isinstance(entry, list):
                continue
            for item in entry:
                if isinstance(item, str) and item not in collected:
                    collected.append(item)
                elif isinstance(item, dict):
                    name = item.get("tool_name") or item.get("name") or item.get("tool")
                    if isinstance(name, str) and name not in collected:
                        collected.append(name)
        return collected

    def _execute_single_pass(
        self,
        dossier: ClaimDossier,
        *,
        pass_role: str = "primary",
        instructions: str | None = None,
        forced_tools: list[str] | None = None,
        session_id: str | None = None,
    ) -> tuple[VerifierPassResult, AgentRunResult[VerifierPassResult]]:
        if forced_tools:
            unknown = [name for name in forced_tools if name not in self._allowed_tool_names]
            if unknown:
                raise ValueError(
                    f"forced_tools {unknown!r} are not registered READ_ONLY verifier tools."
                )

        runtime = self._ensure_runtime()
        agent = Agent(
            runtime=runtime,
            agent_id=self.agent_id,
            model=self.model,
            instructions=instructions or self._build_instructions(pass_role),
            tools=list(self.tools),
            forced_tools=forced_tools,
            output_type=VerifierPassResult,
        )
        run_result = agent.run(
            self._build_prompt(dossier, pass_role),
            session_id=session_id,
            approval_callback=self._read_only_approval_guard,
        )
        output = run_result.output
        if not isinstance(output, VerifierPassResult):
            output = VerifierPassResult.model_validate(output)
        return output, run_result

    def audit_single_pass(
        self,
        dossier: ClaimDossier,
        *,
        pass_role: str = "primary",
        instructions: str | None = None,
        forced_tools: list[str] | None = None,
        session_id: str | None = None,
    ) -> VerifierPassResult:
        """Execute one structured verifier pass using real openminion Agent + READ_ONLY tools."""
        pass_result, _ = self._execute_single_pass(
            dossier,
            pass_role=pass_role,
            instructions=instructions,
            forced_tools=forced_tools,
            session_id=session_id,
        )
        return pass_result

    def audit_claim(
        self,
        dossier: ClaimDossier,
        *,
        single_pass: bool = True,
        session_id: str | None = None,
    ) -> AuditRunBundle:
        """Run a claim audit and emit an AuditRunBundle (single-pass baseline in C1)."""
        del single_pass  # Expanded to multi-pass consensus + handoff in C2.
        pass_result, run_result = self._execute_single_pass(
            dossier,
            pass_role="primary",
            session_id=session_id,
        )
        tool_calls = self._extract_tool_calls(run_result)
        consensus = ConsensusVerdict(
            claim_id=dossier.claim_id,
            final_verdict=pass_result.verdict,
            agreement_score=1.0,
            mean_confidence=pass_result.confidence,
            disagreement_summary="Single-pass verification completed.",
            passes=[pass_result],
            requires_human_review=(pass_result.verdict == "INCONCLUSIVE"),
        )
        return AuditRunBundle(
            claim_id=dossier.claim_id,
            preset=self.preset,
            dossier=dossier,
            consensus=consensus,
            tool_calls=tool_calls,
            run_id=run_result.run_id,
            session_id=run_result.session_id,
            metadata={
                "run_state": run_result.run_state,
                "stats": run_result.stats,
            },
        )
