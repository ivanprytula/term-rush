"""A persisted document chunk: the RAG/analytics corpus (ADR-0018 Slice 1).

Chunking happens in pipeline-service; content-service just stores what it
produces, the same split as terms (pipeline enriches, content-service
persists).
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field

from content_service.domain import constants


class DocumentChunk(BaseModel):
    """One slice of a document's text, with provenance down to the
    character range.

    `id` is a store-assigned identity, None until persisted — same pattern
    as ReviewCandidate.id.
    """

    id: int | None = None
    text: str = Field(min_length=1, max_length=constants.DOCUMENT_CHUNK_MAX_LEN)
    source_file: str = Field(max_length=constants.DOCUMENT_CHUNK_SOURCE_FILE_MAX_LEN)
    chunk_index: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
