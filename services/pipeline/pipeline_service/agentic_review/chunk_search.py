"""REST client for content-service's chunk search (ADR-0012), mirroring
game-service's ChunkSearchPort — but REST/httpx, not gRPC, since
pipeline-service already reaches content-service that way (load.py,
ADR-0004's service-isolation rule).
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel


class RetrievedChunk(BaseModel, frozen=True):
    text: str
    source_file: str


async def search_document_chunks(
    client: httpx.AsyncClient,
    content_service_url: str,
    query: str,
    top_k: int,
) -> tuple[RetrievedChunk, ...]:
    """Semantic search against content-service's document-chunk corpus.

    Never raises on a failed search — returns () the same way
    game-service's ChunkSearchPort does, since a retrieval miss is a
    normal outcome for a LangGraph node to reason about, not a pipeline
    failure.
    """
    try:
        response = await client.get(
            f"{content_service_url}/document-chunks/search",
            params={"query": query, "top_k": top_k},
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return ()

    return tuple(
        RetrievedChunk(text=chunk["text"], source_file=chunk["source_file"])
        for chunk in response.json()["chunks"]
    )
