"""Dagster assets: chunk intake PDFs and submit them to content-service's
document-chunks store (ADR-0018 Slice 1).

Separate chain from the term-candidate pipeline (definitions.py) - this
produces the RAG/analytics corpus, not TermCandidates, and has no
enrich/validate stage since chunking is deterministic (ADR-0004's Extract
stage only; nothing here needs an LLM).

Pipeline: intake_documents (find + OCR-or-text-layer extract) ->
document_chunks (fixed-size split) -> ingested_chunks (submit to
content-service).
"""

from pathlib import Path

import dagster as dg
import httpx
from dagster import AssetExecutionContext

from pipeline_service.config import settings
from pipeline_service.document_ingestion.chunking import DocumentChunk
from pipeline_service.document_ingestion.chunking import chunk_document
from pipeline_service.document_ingestion.document_text import extract_text_from_document
from pipeline_service.document_ingestion.document_text import find_intake_documents
from pipeline_service.document_ingestion.load import ChunkIngestionRejected
from pipeline_service.document_ingestion.load import submit_chunks


@dg.asset(
    group_name="document_ingestion",
    description="Full text of every PDF in the intake directory, keyed by "
    "source file path.",
    dagster_type=dg.Any,  # type: ignore  # variadic tuple; see candidates.py
)
def intake_documents(context: AssetExecutionContext) -> tuple[tuple[str, str], ...]:
    """Extract stage: read every intake PDF's text (text layer or OCR
    fallback). Returns (source_file, text) pairs rather than a dict so the
    tuple stays Dagster's IO-manager-friendly shape, same as every other
    asset in this pipeline.
    """
    intake_dir = Path(settings.DOCUMENT_INTAKE_DIR)
    documents = tuple(
        (str(path), extract_text_from_document(path))
        for path in find_intake_documents(intake_dir)
    )

    context.add_output_metadata({"document_count": len(documents)})
    context.log.info("Extracted text from %d document(s)", len(documents))

    return documents


@dg.asset(
    group_name="document_ingestion",
    description="Fixed-size, overlapping chunks of every intake document's text.",
    dagster_type=dg.Any,  # type: ignore  # variadic tuple; see candidates.py
    ins={"intake_documents": dg.AssetIn(dagster_type=dg.Any)},
)
def document_chunks(
    context: AssetExecutionContext,
    intake_documents: tuple[tuple[str, str], ...],
) -> tuple[DocumentChunk, ...]:
    """Split each document's text into chunks (chunking.py's fixed-size,
    overlapping split - no sentence/paragraph awareness yet).
    """
    chunks = tuple(
        chunk
        for source_file, text in intake_documents
        for chunk in chunk_document(text, source_file)
    )

    context.add_output_metadata({"chunk_count": len(chunks)})
    context.log.info("Produced %d chunk(s)", len(chunks))

    return chunks


@dg.asset(
    group_name="document_ingestion",
    description="Ids of every chunk submitted to content-service's "
    "document-chunks store.",
    dagster_type=dg.Any,  # type: ignore  # variadic tuple; see candidates.py
    ins={"document_chunks": dg.AssetIn(dagster_type=dg.Any)},
)
async def ingested_chunks(
    context: AssetExecutionContext,
    document_chunks: tuple[DocumentChunk, ...],
) -> tuple[int, ...]:
    """Load stage: POST all chunks to content-service in one batch.

    Unlike loaded_candidates (terms), a rejection here fails the run
    outright rather than being skipped - chunks have no per-item review
    path, so there's nothing to do with a partial rejection except retry
    the whole batch.
    """
    if not document_chunks:
        context.log.info("No chunks to submit")
        return ()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            ids = await submit_chunks(
                client, settings.CONTENT_SERVICE_URL, document_chunks
            )
        except ChunkIngestionRejected as exc:
            context.log.error("content-service rejected the chunk batch: %s", exc)
            raise

    context.add_output_metadata({"submitted_count": len(ids)})
    context.log.info("Submitted %d chunk(s) for ingestion", len(ids))

    return ids
