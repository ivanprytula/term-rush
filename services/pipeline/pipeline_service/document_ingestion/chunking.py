"""Split document text into overlapping chunks for the RAG corpus
(ADR-0018 Slice 1: chunk + persist, no embeddings yet).

Fixed-size chunking with overlap - the boring, explicit choice. No sentence-
or paragraph-aware splitting: that's a real improvement worth making once
retrieval quality (Slice 2) can actually measure whether it helps, not
before.
"""

from __future__ import annotations

from pydantic import BaseModel

CHUNK_SIZE_CHARS = 1000
CHUNK_OVERLAP_CHARS = 150


class DocumentChunk(BaseModel):
    """One slice of a document's text, with provenance down to the
    character range - the same discipline TermCandidate has for tokens.
    """

    model_config = {"frozen": True}

    text: str
    source_file: str
    chunk_index: int
    char_start: int
    char_end: int


def chunk_document(text: str, source_file: str) -> tuple[DocumentChunk, ...]:
    """Split text into fixed-size, overlapping chunks.

    Empty text yields no chunks. The last chunk is whatever remains, even
    if shorter than CHUNK_SIZE_CHARS - not padded, not dropped.
    """
    if not text:
        return ()

    stride = CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS
    chunks: list[DocumentChunk] = []
    start = 0
    index = 0

    while start < len(text):
        end = min(start + CHUNK_SIZE_CHARS, len(text))
        chunks.append(
            DocumentChunk(
                text=text[start:end],
                source_file=source_file,
                chunk_index=index,
                char_start=start,
                char_end=end,
            )
        )
        if end == len(text):
            break
        start += stride
        index += 1

    return tuple(chunks)
