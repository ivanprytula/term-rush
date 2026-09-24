"""Dagster asset: enriched knowledge objects, one per extracted candidate."""

from pathlib import Path

import dagster as dg
from anthropic import AsyncAnthropic
from dagster import AssetExecutionContext

from pipeline_service.candidate import TermCandidate
from pipeline_service.candidate import confidence_rank
from pipeline_service.config import settings
from pipeline_service.curated import load_curated_terms
from pipeline_service.enrich import AnthropicEnricher
from pipeline_service.enriched_term import EnrichedTerm
from pipeline_service.repo_context import find_usage_snippets
from pipeline_service.validate import normalized_term_key

REPO_ROOT = Path(__file__).resolve().parents[4]


@dg.asset(
    group_name="enrich",
    description="Drafted knowledge objects for every extracted candidate, plus "
    "the hand-authored curated source.",
    dagster_type=dg.Any,  # type: ignore  # variadic tuple; see candidates.py
    ins={
        "dependency_manifest_candidates": dg.AssetIn(dagster_type=dg.Any),
        "adr_heading_candidates": dg.AssetIn(dagster_type=dg.Any),
        "class_name_candidates": dg.AssetIn(dagster_type=dg.Any),
    },
)
async def enriched_candidates(
    context: AssetExecutionContext,
    dependency_manifest_candidates: tuple[TermCandidate, ...],
    adr_heading_candidates: tuple[TermCandidate, ...],
    class_name_candidates: tuple[TermCandidate, ...],
) -> tuple[tuple[EnrichedTerm, TermCandidate], ...]:
    """Enrich stage: one LLM call per extracted candidate, grounded by a
    small amount of real repo usage (ADR-0004). Pairs each drafted term
    with the candidate it came from — downstream (load) needs both,
    since submission provenance lives on TermCandidate, not EnrichedTerm.

    The curated source (ADR-0004: hand-authored, no extraction) skips
    the LLM call entirely — a human already wrote the knowledge object,
    so its pairs are read from curated_terms.yaml and merged in
    directly. It still goes through the same dedup: a term named by
    both an extracted source and the curated list keeps the curated
    entry, since CURATED outranks every extracted confidence level.

    Every source is deduplicated by the same normalized key validate's
    batch contract uses (TCP/IP == TCP IP) — so a term named twice
    enriches/loads once. Ties broken by explicit confidence rank, not
    merge-expression order, so adding another source can't silently
    change which candidate wins.
    """
    enricher = AnthropicEnricher(AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY))

    curated_pairs = load_curated_terms()
    curated_by_key: dict[str, tuple[EnrichedTerm, TermCandidate]] = {}
    for term, candidate in curated_pairs:
        key = normalized_term_key(candidate.name)
        if key in curated_by_key:
            raise dg.Failure(
                description=f"curated_terms.yaml has a duplicate term: {candidate.name!r}"
            )
        curated_by_key[key] = (term, candidate)

    extracted_candidates = sorted(
        dependency_manifest_candidates + adr_heading_candidates + class_name_candidates,
        key=lambda c: confidence_rank(c.confidence),
    )
    deduped_extracted: dict[str, TermCandidate] = {}
    for candidate in extracted_candidates:
        deduped_extracted.setdefault(normalized_term_key(candidate.name), candidate)

    results: list[tuple[EnrichedTerm, TermCandidate]] = list(curated_by_key.values())
    for key, candidate in deduped_extracted.items():
        if key in curated_by_key:
            continue  # curated already covers this term at higher confidence
        snippets = find_usage_snippets(candidate.name, REPO_ROOT)
        term = await enricher.enrich(candidate, snippets)
        results.append((term, candidate))

    context.add_output_metadata({"enriched_count": len(results)})
    context.log.info("Enriched %d candidates", len(results))

    return tuple(results)
