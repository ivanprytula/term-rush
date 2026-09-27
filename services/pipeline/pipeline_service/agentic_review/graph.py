"""LangGraph agent slice (ADR-0019). Slice 4: retrieve -> draft ->
critique (bounded loop) -> submit_for_review, checkpointed.

Human-in-the-loop happens through the review queue itself (ADR-0004),
not a resumed graph run: submit_for_review POSTs the accepted draft to
content-service's existing PENDING queue and the graph ends there - "the
graph halts, the existing queue is where a human sees it" (ADR-0019).
There is nothing to resume; approval/rejection happens out-of-band
through the review-queue UI, on a different row than this graph run.

Checkpointing (SQLite, via AsyncSqliteSaver) exists so a crashed run
resumes from its last completed node - retrieve/draft/critique/submit -
rather than re-running the whole graph, including redundant LLM calls,
after an ordinary process restart.
"""

from __future__ import annotations

from typing import TypedDict

import httpx
from anthropic import AsyncAnthropic
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END
from langgraph.graph import StateGraph

from pipeline_service.agentic_review.chunk_search import RetrievedChunk
from pipeline_service.agentic_review.chunk_search import search_document_chunks
from pipeline_service.agentic_review.critique import AgenticCritic
from pipeline_service.agentic_review.draft import AgenticDrafter
from pipeline_service.candidate import TermCandidate
from pipeline_service.enriched_term import EnrichedTerm
from pipeline_service.load import ReviewCandidateRejected
from pipeline_service.load import submit_for_review

RETRIEVE_TOP_K = 5
MAX_RETRIEVAL_PASSES = 3


class AgenticReviewState(TypedDict):
    """State threaded through the graph. query starts as the candidate
    name; critique may rewrite it for a refined retry, bounded by
    retrieval_passes. review_candidate_id is set once submit_for_review
    completes - None until then, and also None if content-service
    rejected the submission outright.
    """

    candidate: TermCandidate
    query: str
    retrieved_chunks: tuple[RetrievedChunk, ...]
    draft: EnrichedTerm | None
    retrieval_passes: int
    accepted: bool
    review_candidate_id: int | None


def build_agentic_review_graph(
    client: httpx.AsyncClient,
    content_service_url: str,
    anthropic_client: AsyncAnthropic,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Compile the Slice-4 graph: retrieve -> draft -> critique (bounded
    loop) -> submit_for_review. checkpointer is required to actually
    persist state across process restarts; omit only for a single
    in-process run where checkpointing doesn't matter (e.g. tests).
    """
    drafter = AgenticDrafter(anthropic_client)
    critic = AgenticCritic(anthropic_client)

    async def retrieve(state: AgenticReviewState) -> AgenticReviewState:
        chunks = await search_document_chunks(
            client, content_service_url, state["query"], RETRIEVE_TOP_K
        )
        return {
            **state,
            "retrieved_chunks": chunks,
            "retrieval_passes": state["retrieval_passes"] + 1,
        }

    async def draft(state: AgenticReviewState) -> AgenticReviewState:
        drafted = await drafter.draft(state["candidate"], state["retrieved_chunks"])
        return {**state, "draft": drafted}

    async def critique(state: AgenticReviewState) -> AgenticReviewState:
        assert state["draft"] is not None
        if state["retrieval_passes"] >= MAX_RETRIEVAL_PASSES:
            return {**state, "accepted": True}

        result = await critic.critique(
            state["candidate"], state["draft"], state["retrieved_chunks"]
        )
        if result.accept:
            return {**state, "accepted": True}
        assert result.refined_query is not None
        return {**state, "accepted": False, "query": result.refined_query}

    async def submit_review(state: AgenticReviewState) -> AgenticReviewState:
        assert state["draft"] is not None
        try:
            candidate_id = await submit_for_review(
                client, content_service_url, state["draft"], state["candidate"]
            )
        except ReviewCandidateRejected:
            return {**state, "review_candidate_id": None}
        return {**state, "review_candidate_id": candidate_id}

    def route_after_critique(state: AgenticReviewState) -> str:
        return "submit_review" if state["accepted"] else "retrieve"

    graph = StateGraph(AgenticReviewState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("draft", draft)
    graph.add_node("critique", critique)
    graph.add_node("submit_review", submit_review)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", "critique")
    graph.add_conditional_edges(
        "critique",
        route_after_critique,
        {"submit_review": "submit_review", "retrieve": "retrieve"},
    )
    graph.add_edge("submit_review", END)
    return graph.compile(checkpointer=checkpointer)
