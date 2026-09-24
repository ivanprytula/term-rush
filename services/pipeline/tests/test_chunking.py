"""Tests for document chunking (ADR-0018 Slice 1)."""

from __future__ import annotations

from pipeline_service.document_ingestion.chunking import CHUNK_OVERLAP_CHARS
from pipeline_service.document_ingestion.chunking import CHUNK_SIZE_CHARS
from pipeline_service.document_ingestion.chunking import chunk_document


def test_chunk_document_empty_text_yields_no_chunks() -> None:
    assert chunk_document("", "contract.pdf") == ()


def test_chunk_document_short_text_yields_one_chunk() -> None:
    text = "short text"

    chunks = chunk_document(text, "contract.pdf")

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].chunk_index == 0
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)


def test_chunk_document_sets_source_file_on_every_chunk() -> None:
    text = "x" * (CHUNK_SIZE_CHARS * 2)

    chunks = chunk_document(text, "contract.pdf")

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.source_file == "contract.pdf"


def test_chunk_document_splits_long_text_into_multiple_chunks() -> None:
    text = "x" * (CHUNK_SIZE_CHARS * 2)

    chunks = chunk_document(text, "contract.pdf")

    assert len(chunks) > 1
    assert all(len(c.text) <= CHUNK_SIZE_CHARS for c in chunks)


def test_chunk_document_consecutive_chunks_overlap() -> None:
    text = "x" * (CHUNK_SIZE_CHARS * 2)

    chunks = chunk_document(text, "contract.pdf")

    first, second = chunks[0], chunks[1]
    assert second.char_start == first.char_start + (
        CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS
    )
    overlap_len = first.char_end - second.char_start
    assert overlap_len == CHUNK_OVERLAP_CHARS


def test_chunk_document_last_chunk_is_not_padded() -> None:
    text = "x" * (CHUNK_SIZE_CHARS + 50)

    chunks = chunk_document(text, "contract.pdf")

    last = chunks[-1]
    assert last.char_end == len(text)
    assert len(last.text) < CHUNK_SIZE_CHARS


def test_chunk_document_indices_are_sequential() -> None:
    text = "x" * (CHUNK_SIZE_CHARS * 3)

    chunks = chunk_document(text, "contract.pdf")

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_document_covers_full_text_with_no_gaps() -> None:
    text = "".join(str(i % 10) for i in range(CHUNK_SIZE_CHARS * 3))

    chunks = chunk_document(text, "contract.pdf")

    # Every character position is covered by at least one chunk.
    covered = set()
    for chunk in chunks:
        covered.update(range(chunk.char_start, chunk.char_end))
    assert covered == set(range(len(text)))
