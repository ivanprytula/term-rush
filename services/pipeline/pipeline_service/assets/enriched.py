"""Dagster asset: enriched knowledge objects, one per extracted candidate."""

from pathlib import Path

import dagster as dg
from anthropic import AsyncAnthropic
from dagster import AssetExecutionContext

from pipeline_service.candidate import TermCandidate
from pipeline_service.config import settings
from pipeline_service.enrich import AnthropicEnricher
from pipeline_service.enriched_term import EnrichedTerm
from pipeline_service.repo_context import find_usage_snippets

REPO_ROOT = Path(__file__).resolve().parents[4]


@dg.asset(
    group_name="enrich",
    description="Drafted knowledge objects for every extracted candidate.",
    dagster_type=dg.Any,  # type: ignore  # variadic tuple; see candidates.py
    ins={"dependency_manifest_candidates": dg.AssetIn(dagster_type=dg.Any)},
)
async def enriched_candidates(
    context: AssetExecutionContext,
    dependency_manifest_candidates: tuple[TermCandidate, ...],
) -> tuple[tuple[EnrichedTerm, TermCandidate], ...]:
    """Enrich stage: one LLM call per candidate, grounded by a small
    amount of real repo usage (ADR-0004). Pairs each drafted term with
    the candidate it came from — downstream (load) needs both, since
    submission provenance lives on TermCandidate, not EnrichedTerm.
    """
    enricher = AnthropicEnricher(AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY))
    results: list[tuple[EnrichedTerm, TermCandidate]] = []

    for candidate in dependency_manifest_candidates:
        snippets = find_usage_snippets(candidate.name, REPO_ROOT)
        term = await enricher.enrich(candidate, snippets)
        results.append((term, candidate))

    context.add_output_metadata({"enriched_count": len(results)})
    context.log.info("Enriched %d candidates", len(results))

    return tuple(results)
