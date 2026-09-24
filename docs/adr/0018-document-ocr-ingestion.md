# ADR-0018: Document ingestion as a chunked RAG/analytics corpus

- **Status:** Accepted
- **Date:** 2026-09-24
- **Related:** ADR-0004 (term bank - unaffected; term-candidate extraction
  from documents stays available but secondary, see below), ADR-0012
  (pgvector for this corpus, once Slice 2 ships)

## Context

Every extraction source in ADR-0004 is repo-native: dependency manifests, ADR
headings, class names, a hand-curated list. That demonstrates a multi-source
pipeline, but not a specific, in-demand capability: turning unstructured
business documents (PDFs, scanned forms, contracts) into a queryable data
asset. "Generative AI data integration" job postings consistently describe
exactly this - ingesting messy documents nobody previously mined to unlock
insight. The project had no extractor that showed it.

This ADR's first version (2026-09-24, same day) framed document ingestion as
one more Extract-stage source feeding the term bank: OCR a PDF, pull
capitalized tokens, run them through the existing enrich/validate/review/load
pipeline like any other `SourceType`. That shipped
(`pipeline_service/extractors/document_ocr.py`), is tested, and works.

**It was the wrong target.** The point of demonstrating "data integration" is
a queryable corpus that unlocks insight - not a handful of flashcard terms
skimmed off a contract's capitalized words. Revised before the rest of the
pipeline was built: document ingestion's primary output is a **chunked,
provenance-carrying text corpus** for RAG/analytics. Term-candidate
extraction remains available - the OCR mechanics are shared, not
duplicated - but it's now an optional secondary path over the same text, not
the reason this exists.

## Decision

**Documents are ingested, OCR'd where needed, chunked, and persisted with
provenance. That chunk store is the primary deliverable. Term-candidate
extraction (`document_ocr.py`, unchanged) remains a secondary, optional
consumer of the same OCR'd text.**

- Intake is `docs/source-documents/` - a directory populated by hand, not a
  repo-wide glob. Bounded, deliberate, reviewable - unchanged from v1.
- OCR: `pypdf` text-layer extraction first, `pytesseract` + `pdf2image` as
  the scanned-page fallback - unchanged from v1. This logic is factored into
  a shared `extract_text_from_document()` so both consumers (chunking,
  term-candidate extraction) call one OCR path, not two.
- Chunking: fixed-size chunks with overlap, each carrying `source_file`,
  `chunk_index`, and a character range - the same provenance discipline
  `TermCandidate` already has, applied to prose instead of tokens.
- Storage: content-service owns the persisted `document_chunks` table,
  mirroring how it already owns the term store and review-queue -
  pipeline-service produces, content-service persists. No embeddings in
  this slice; chunks are stored as plain text with metadata, queryable by
  source/keyword. That's a real, demoable intermediate state, not a
  placeholder.
- Term-candidate extraction stays exactly as built in v1 - `document_ocr.py`
  is untouched except to call the shared OCR function instead of its own
  inline logic. It is not the pipeline's primary output anymore, but it's
  not deleted or degraded either.

### Why classical OCR, not a vision-LLM call

Unchanged from v1: provenance has to mean "this text was mechanically pulled
from page N, character range X-Y," not "the model said so." A vision-LLM
call would make chunk provenance unauditable in the same way it would have
made term-candidate provenance unauditable. OCR output feeding an LLM
*downstream* (an enrichment or retrieval step, later) is fine; OCR *being*
an LLM call is not, for the same reason ADR-0004's Extract stage stays
deterministic.

### Slice sequencing

This ADR ships in slices, each independently useful, none blocking the last:

- **Slice 1 (this increment):** ingest → OCR → chunk → persist. No
  embeddings, no vector search. Chunks are queryable by source file and
  keyword through content-service's API.
- **Slice 2:** embeddings over the persisted chunks, stored in pgvector
  (ADR-0012). Turns Slice 1's chunk store into genuine semantic search.
- **Slice 3:** an analytics/insight surface over the corpus - aggregate
  queries, dashboards, or an LLM-backed Q&A layer. Only makes sense once
  Slice 2 exists to retrieve against. May land in ADR-0005's dbt/warehouse
  layer rather than as a new system, depending on shape at the time.

## Consequences

**Good:**

- A genuinely demoable "unstructured document → queryable corpus" story -
  the actual shape of the JD language that motivated this work, not an
  approximation of it
- Slice 1 ships without waiting on embeddings/vector search decisions -
  those are real, separately-justified increments (ADR-0012), not a
  precondition
- Term-candidate extraction (v1's work) isn't wasted - same OCR mechanics,
  now a documented secondary path instead of the whole story

**Bad:**

- `pytesseract`/`pdf2image` still need system binaries beyond the Python
  dependency - unchanged concern from v1, Docker image follow-up still
  pending
- A second consumer (content-service) and a new table/migration/API is a
  materially bigger increment than v1's single-module extractor - the
  "ship one module at a time" discipline applies within this slice too:
  chunking logic, then storage, then wiring, reviewed separately
- Un-embedded chunk storage (Slice 1) has limited retrieval quality on its
  own (keyword search over chunks, not semantic) - acceptable as an honest
  intermediate state, not oversold as "RAG" until Slice 2 lands

## Alternatives considered

**Keep v1's term-bank framing, add chunking as a separate, later ADR.**
Rejected: the term-bank framing was decided same-day, before any of Slices
2/3 were built on top of it - correcting course now is cheaper than
shipping a chunking pipeline on top of a decision already known to be
wrong, and cheaper than running two documents that both claim to be "the"
document-ingestion ADR.

**Vision-LLM extraction directly to structured chunks/insights.** Rejected
for the same reason as v1: collapses extraction and understanding into one
unauditable step. Worth revisiting as a Slice 3 retrieval-augmented
generation layer, once there's a real corpus to ground it in.

## When I would change this

- If Slice 1's chunk store proves to have real query patterns that keyword
  search satisfies fine, Slice 2 (embeddings) may not be worth building -
  that's a legitimate outcome, not a failure to reach it.
- If a second document format is genuinely needed (DOCX contracts, HTML
  exports), generalize the OCR/chunking interface then - not speculatively
  now.
- If handwritten-document ingestion becomes the actual target, that is a
  distinct extractor with its own accuracy story, not a silent extension of
  this one.
- If the hand-populated intake directory's document volume grows past a
  handful of files, that's the trigger for a real upload/ingestion path,
  not before.
