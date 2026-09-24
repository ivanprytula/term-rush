"""Dagster asset: enriched knowledge objects, one per extracted candidate."""

from pathlib import Path

import dagster as dg
from anthropic import AsyncAnthropic
from dagster import AssetExecutionContext

from pipeline_service.candidate import TermCandidate
from pipeline_service.candidate import confidence_rank
from pipeline_service.config import settings
from pipeline_service.enrich import AnthropicEnricher
from pipeline_service.enriched_term import EnrichedTerm
from pipeline_service.repo_context import find_usage_snippets
from pipeline_service.validate import normalized_term_key

REPO_ROOT = Path(__file__).resolve().parents[4]


@dg.asset(
    group_name="enrich",
    description="Drafted knowledge objects for every extracted candidate.",
    dagster_type=dg.Any,  # type: ignore  # variadic tuple; see candidates.py
    ins={
        "dependency_manifest_candidates": dg.AssetIn(dagster_type=dg.Any),
        "adr_heading_candidates": dg.AssetIn(dagster_type=dg.Any),
    },
)
async def enriched_candidates(
    context: AssetExecutionContext,
    dependency_manifest_candidates: tuple[TermCandidate, ...],
    adr_heading_candidates: tuple[TermCandidate, ...],
) -> tuple[tuple[EnrichedTerm, TermCandidate], ...]:
    """Enrich stage: one LLM call per candidate, grounded by a small
    amount of real repo usage (ADR-0004). Pairs each drafted term with
    the candidate it came from — downstream (load) needs both, since
    submission provenance lives on TermCandidate, not EnrichedTerm.

    Merges every extract-stage source, deduplicated by the same
    normalized key validate's batch contract uses (TCP/IP == TCP IP) —
    so a term named by two sources enriches once. Ties broken by
    explicit confidence rank (ADR-0004's High/Medium/Low), not by
    merge-expression order, so adding a third source can't silently
    change which candidate wins.
    """
    enricher = AnthropicEnricher(AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY))
    results: list[tuple[EnrichedTerm, TermCandidate]] = []

    all_candidates = sorted(
        dependency_manifest_candidates + adr_heading_candidates,
        key=lambda c: confidence_rank(c.confidence),
    )
    deduped: dict[str, TermCandidate] = {}
    for candidate in all_candidates:
        deduped.setdefault(normalized_term_key(candidate.name), candidate)

    for candidate in deduped.values():
        snippets = find_usage_snippets(candidate.name, REPO_ROOT)
        term = await enricher.enrich(candidate, snippets)
        results.append((term, candidate))

    context.add_output_metadata({"enriched_count": len(results)})
    context.log.info("Enriched %d candidates", len(results))

    return tuple(results)
