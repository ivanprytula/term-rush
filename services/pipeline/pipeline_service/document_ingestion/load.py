"""Load: submit chunked document text to content-service's document-chunks
store (ADR-0018 Slice 1).

REST, not a shared DB connection - same cross-service boundary load.py
already crosses for terms; content-service owns document_chunks, this is
just another caller.
"""

from __future__ import annotations

import httpx

from pipeline_service.document_ingestion.chunking import DocumentChunk


class ChunkIngestionRejected(Exception):
    """content-service refused the batch (e.g. 422 on a malformed chunk) -
    distinct from a network/connectivity failure, which raises httpx's own
    exception types instead.
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"content-service rejected chunk batch: {status_code} {body}")


def _batch_payload(chunks: tuple[DocumentChunk, ...]) -> dict:
    return {
        "chunks": [
            {
                "text": c.text,
                "source_file": c.source_file,
                "chunk_index": c.chunk_index,
                "char_start": c.char_start,
                "char_end": c.char_end,
            }
            for c in chunks
        ]
    }


async def submit_chunks(
    client: httpx.AsyncClient,
    content_service_url: str,
    chunks: tuple[DocumentChunk, ...],
) -> tuple[int, ...]:
    """POST a batch of chunks to content-service's /document-chunks.
    Returns the assigned ids, same order as the input.

    Raises ChunkIngestionRejected on a 4xx; httpx's own exceptions
    (ConnectError, TimeoutException, ...) propagate for connectivity
    failures - same split load.py makes for term submissions.
    """
    response = await client.post(
        f"{content_service_url}/document-chunks",
        json=_batch_payload(chunks),
    )
    if response.status_code >= 400:
        raise ChunkIngestionRejected(response.status_code, response.text)
    return tuple(c["id"] for c in response.json()["chunks"])
