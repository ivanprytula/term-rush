"""Dagster asset: LangGraph agent slice (ADR-0019), Slice 4.

Runs retrieve -> draft -> critique (bounded loop) -> submit_for_review
per validated candidate, checkpointed to SQLite so a crashed run resumes
from its last completed node instead of restarting the whole graph.
Human-in-the-loop happens through the review queue's existing PENDING
state (ADR-0004), not a resumed graph - the graph's job ends at
submission. This asset runs alongside loaded_candidates, not instead of
it (ADR-0019: additive) - the two independently submit to the same
review queue via different paths (deterministic enrich vs. agentic
retrieve/draft/critique).
"""

import dagster as dg
import httpx
from anthropic import AsyncAnthropic
from dagster import AssetExecutionContext
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from pipeline_service.agentic_review.graph import build_agentic_review_graph
from pipeline_service.candidate import TermCandidate
from pipeline_service.config import settings
from pipeline_service.enriched_term import EnrichedTerm
from pipeline_service.validate import normalized_term_key


@dg.asset(
    group_name="agentic_review",
    description="Slice-4 ADR-0019 LangGraph agent: retrieve -> draft -> "
    "critique (bounded loop) -> submit_for_review per validated candidate, "
    "checkpointed to SQLite. Submits accepted drafts to the same review "
    "queue loaded_candidates does.",
    dagster_type=dg.Any,  # type: ignore  # variadic tuple; see candidates.py
    ins={"validated_candidates": dg.AssetIn(dagster_type=dg.Any)},
)
async def agentic_review_candidates(
    context: AssetExecutionContext,
    validated_candidates: tuple[tuple[EnrichedTerm, TermCandidate], ...],
) -> tuple[int, ...]:
    """One retrieve -> draft -> critique -> submit_for_review graph run
    per validated candidate. Returns the review-queue candidate id for
    every accepted submission; a candidate content-service rejects is
    logged and skipped, same posture loaded_candidates takes.
    """
    submitted_ids: list[int] = []
    rejected: list[str] = []

    async with (
        httpx.AsyncClient(timeout=10.0) as client,
        AsyncSqliteSaver.from_conn_string(
            settings.AGENTIC_REVIEW_CHECKPOINT_DB
        ) as checkpointer,
    ):
        anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        graph = build_agentic_review_graph(
            client, settings.CONTENT_SERVICE_URL, anthropic_client, checkpointer
        )
        for term, candidate in validated_candidates:
            thread_id = normalized_term_key(candidate.name)
            result = await graph.ainvoke(
                {
                    "candidate": candidate,
                    "query": term.term,
                    "retrieved_chunks": (),
                    "draft": None,
                    "retrieval_passes": 0,
                    "accepted": False,
                    "review_candidate_id": None,
                },
                config={"configurable": {"thread_id": thread_id}},
            )
            if result["review_candidate_id"] is None:
                rejected.append(candidate.name)
                continue
            submitted_ids.append(result["review_candidate_id"])

    if rejected:
        context.log.warning(
            "%d candidate(s) rejected by content-service: %s",
            len(rejected),
            ", ".join(rejected),
        )

    context.add_output_metadata(
        {
            "submitted_count": len(submitted_ids),
            "rejected_count": len(rejected),
        }
    )
    context.log.info(
        "Submitted %d/%d agentic candidates for review",
        len(submitted_ids),
        len(validated_candidates),
    )

    return tuple(submitted_ids)
