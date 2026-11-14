"""Pydantic v2 domain models for Claim Dossiers, Verifier Passes, Consensus, and Probes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VerdictLiteral = Literal["SUPPORTED", "REFUTED", "INCONCLUSIVE"]


class EvidenceCitation(BaseModel):
    """Single source citation supporting or refuting a claim."""

    source_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    url: str | None = None
    excerpt: str = Field(..., min_length=1)
    published_at: str | None = None


class ClaimDossier(BaseModel):
    """Structured package of claim text, market question, and resolution rules."""

    claim_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    claim: str = Field(..., min_length=1)
    market_question: str = Field(..., min_length=1)
    resolution_criteria: str = ""
    source_hints: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerifierPassResult(BaseModel):
    """Structured output returned by a single openminion verifier pass."""

    verdict: VerdictLiteral
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(..., min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)
    pass_role: str = Field(default="primary", min_length=1)


class ConsensusVerdict(BaseModel):
    """Aggregated outcome synthesized across one or more verifier passes."""

    claim_id: str = Field(..., min_length=1)
    final_verdict: VerdictLiteral
    agreement_score: float = Field(..., ge=0.0, le=1.0)
    mean_confidence: float = Field(..., ge=0.0, le=1.0)
    disagreement_summary: str = ""
    passes: list[VerifierPassResult] = Field(default_factory=list)
    requires_human_review: bool = False


class AuditRunBundle(BaseModel):
    """Complete audit artifact emitted for CLI output, verification, and replay."""

    claim_id: str = Field(..., min_length=1)
    preset: str = Field(..., min_length=1)
    dossier: ClaimDossier
    consensus: ConsensusVerdict
    tool_calls: list[str] = Field(default_factory=list)
    run_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProbeCheckResult(BaseModel):
    """Outcome record for a building-block runtime probe."""

    probe_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    passed: bool
    detail: str = ""
    latency_ms: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
