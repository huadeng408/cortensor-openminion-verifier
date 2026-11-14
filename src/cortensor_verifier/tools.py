"""Read-only @tool functions and ClaimDossier fixture loaders."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from openminion.tools import tool

from cortensor_verifier.models import ClaimDossier


def resolve_default_fixture_path() -> Path:
    """Locate fixtures/claim_dossiers.json relative to the repository or cwd."""
    package_root = Path(__file__).resolve().parents[2]
    candidate = package_root / "fixtures" / "claim_dossiers.json"
    if candidate.exists():
        return candidate
    return Path.cwd() / "fixtures" / "claim_dossiers.json"


def _load_fixture_bundle(fixture_path: str | Path | None = None) -> dict[str, Any]:
    target = Path(fixture_path) if fixture_path is not None else resolve_default_fixture_path()
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Fixture file {target} must decode to a JSON object.")
    return data


def list_claim_ids(fixture_path: str | Path | None = None) -> list[str]:
    """Return available claim_id values from the fixture catalog."""
    bundle = _load_fixture_bundle(fixture_path)
    return [
        str(item["claim_id"])
        for item in bundle.get("dossiers", [])
        if isinstance(item, dict) and item.get("claim_id")
    ]


def load_claim_dossier(
    claim_id: str,
    *,
    fixture_path: str | Path | None = None,
) -> ClaimDossier:
    """Load and validate a ClaimDossier by claim_id from the fixture bundle."""
    bundle = _load_fixture_bundle(fixture_path)
    for raw in bundle.get("dossiers", []):
        if isinstance(raw, dict) and raw.get("claim_id") == claim_id:
            return ClaimDossier.model_validate(raw)
    available = ", ".join(list_claim_ids(fixture_path))
    raise KeyError(f"Unknown claim_id {claim_id!r}. Available fixtures: {available}")


def load_dossier_from_file(path: str | Path) -> ClaimDossier:
    """Load and validate a standalone ClaimDossier JSON file."""
    target = Path(path)
    return ClaimDossier.model_validate_json(target.read_text(encoding="utf-8"))


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9-]+", text.lower()) if len(tok) >= 2}


@tool(min_scope="READ_ONLY", idempotent=True)
def load_delphi_market_fixture(claim_id: str) -> dict[str, Any]:
    """Load a Delphi/prediction-market claim dossier fixture by claim_id."""
    try:
        dossier = load_claim_dossier(claim_id)
    except KeyError as exc:
        return {"found": False, "claim_id": claim_id, "error": str(exc)}
    return {"found": True, "dossier": dossier.model_dump(mode="json")}


@tool(min_scope="READ_ONLY", idempotent=True)
def search_public_evidence(query: str, limit: int = 5) -> dict[str, Any]:
    """Search curated public evidence records matching the query string."""
    bundle = _load_fixture_bundle()
    sources = bundle.get("evidence_sources", [])
    query_tokens = _tokenize(query)
    capped_limit = min(max(int(limit), 1), 10)

    scored: list[tuple[int, dict[str, Any]]] = []
    for record in sources:
        if not isinstance(record, dict):
            continue
        haystack = " ".join(
            [
                str(record.get("source_id", "")),
                str(record.get("title", "")),
                str(record.get("excerpt", "")),
                " ".join(str(kw) for kw in record.get("keywords", [])),
            ]
        )
        record_tokens = _tokenize(haystack)
        overlap = len(query_tokens & record_tokens) if query_tokens else 1
        if overlap > 0:
            scored.append(
                (
                    overlap,
                    {
                        "source_id": record.get("source_id"),
                        "title": record.get("title"),
                        "url": record.get("url"),
                        "published_at": record.get("published_at"),
                        "snippet": str(record.get("excerpt", ""))[:240],
                        "score": overlap,
                    },
                )
            )

    scored.sort(key=lambda item: item[0], reverse=True)
    return {
        "query": query,
        "matches": [item[1] for item in scored[:capped_limit]],
    }


@tool(min_scope="READ_ONLY", idempotent=True)
def fetch_source_excerpt(source_id: str) -> dict[str, Any]:
    """Fetch the full verifiable excerpt and metadata for a public evidence source_id."""
    bundle = _load_fixture_bundle()
    for record in bundle.get("evidence_sources", []):
        if isinstance(record, dict) and record.get("source_id") == source_id:
            return {
                "found": True,
                "source_id": record.get("source_id"),
                "title": record.get("title"),
                "url": record.get("url"),
                "published_at": record.get("published_at"),
                "excerpt": record.get("excerpt"),
            }
    return {"found": False, "source_id": source_id, "error": "Unknown source_id"}


READ_ONLY_VERIFIER_TOOLS: tuple[Any, ...] = (
    load_delphi_market_fixture,
    search_public_evidence,
    fetch_source_excerpt,
)


def assert_read_only_tools(tools: Iterable[Any]) -> list[Any]:
    """Ensure every configured tool declares READ_ONLY min_scope and is non-dangerous."""
    validated: list[Any] = []
    for item in tools:
        decl = getattr(item, "tool_decl", None)
        if decl is None:
            raise ValueError(
                f"Tool {item!r} must be decorated with @tool(min_scope='READ_ONLY')."
            )
        if decl.min_scope != "READ_ONLY" or decl.dangerous:
            raise ValueError(
                f"Tool {decl.name!r} violates READ_ONLY boundary "
                f"(min_scope={decl.min_scope!r}, dangerous={decl.dangerous!r})."
            )
        validated.append(item)
    return validated
