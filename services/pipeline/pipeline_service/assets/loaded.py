"""Dagster asset: submits validated terms to content-service's review queue."""

import dagster as dg
import httpx
from dagster import AssetExecutionContext

from pipeline_service.candidate import TermCandidate
from pipeline_service.config import settings
from pipeline_service.enriched_term import EnrichedTerm
from pipeline_service.load import ReviewCandidateRejected
from pipeline_service.load import submit_for_review


@dg.asset(
    group_name="load",
    description="Review-queue candidate ids for every validated term (ADR-0004: "
    "load writes the review queue, not the live term bank directly).",
    dagster_type=dg.Any,  # type: ignore  # variadic tuple; see candidates.py
    ins={"validated_candidates": dg.AssetIn(dagster_type=dg.Any)},
)
async def loaded_candidates(
    context: AssetExecutionContext,
    validated_candidates: tuple[tuple[EnrichedTerm, TermCandidate], ...],
) -> tuple[int, ...]:
    """Load stage: POST each validated term to content-service's
    /review-queue/candidates over REST (cross-service write, not a
    shared DB connection — same isolation the architecture invariants
    enforce between game-service and content-service).

    A single submission's rejection doesn't fail the run — it's logged
    and skipped, since it means content-service's own request validation
    caught something validate_term didn't (the two aren't required to
    be identical checks). A connectivity failure (content-service down)
    does fail the run — there's nothing useful to do without it.
    """
    submitted_ids: list[int] = []
    rejected: list[str] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        for term, candidate in validated_candidates:
            try:
                candidate_id = await submit_for_review(
                    client, settings.CONTENT_SERVICE_URL, term, candidate
                )
            except ReviewCandidateRejected as exc:
                rejected.append(f"{term.id}: {exc}")
                continue
            submitted_ids.append(candidate_id)

    if rejected:
        context.log.warning(
            "%d candidate(s) rejected by content-service: %s",
            len(rejected),
            "; ".join(rejected),
        )

    context.add_output_metadata(
        {
            "submitted_count": len(submitted_ids),
            "rejected_count": len(rejected),
        }
    )
    context.log.info(
        "Submitted %d/%d candidates for review",
        len(submitted_ids),
        len(validated_candidates),
    )

    return tuple(submitted_ids)
