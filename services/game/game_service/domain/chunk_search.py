"""Semantic search over content-service's RAG document-chunk corpus
(ADR-0012 Slice 2), for grounding the LLM judge's grading context.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    """One chunk of grounding text, with its source for provenance."""

    model_config = {"frozen": True}

    text: str
    source_file: str


class ChunkSearchPort(Protocol):
    """Finds document chunks semantically similar to a query. Implemented
    by an infrastructure adapter (GrpcChunkSearch, over the same gRPC
    channel game-service already uses for term lookup — ADR-0009).
    Declared here, not in application/ports.py, for the same reason
    LLMJudgePort is: a domain-level collaborator, not an application-owned
    repository contract.
    """

    async def search(self, query: str, top_k: int) -> tuple[RetrievedChunk, ...]:
        """The top_k chunks most semantically similar to `query`, closest
        first. Returns an empty tuple on provider failure — retrieval
        grounding is an enhancement to grading, not a precondition for it;
        callers proceed without context rather than failing the grade."""
        ...
