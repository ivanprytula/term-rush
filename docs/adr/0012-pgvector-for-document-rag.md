# ADR-0012: pgvector for document-ingestion RAG

- **Status:** Accepted
- **Date:** 2026-09-24
- **Related:** ADR-0004 (term bank, unaffected by this decision), ADR-0005
  (dbt/warehouse - the chunk store here is operational, not a warehouse
  mart), ADR-0018 (document ingestion - this ADR's trigger)

## Context

This ADR number has been a placeholder since ADR-0005: "pgvector, reserved,
not yet - corpus too small to justify embeddings." Two places in the code
already point at it as a deferred decision:

- `repo_context.py` grounds the enrich-stage LLM prompt with plain `git
  grep`, explicitly not RAG, "proportional to today's scale (a few dozen
  candidates)."
- `skills-map.md`'s Vector store row: "pgvector for semantic term
  similarity + RAG retrieval... not yet implemented."

Both describe the same corpus: **term candidates**, a few dozen short
strings. That corpus is still too small for embeddings to earn their cost -
nothing here changes that.

Document ingestion (ADR-0018) is a different corpus. A handful of PDF
documents, each split into many chunks of prose, is chunked freeform text
from day one - not a few dozen short tokens. Grep grounding doesn't
transfer: there's no known-identifier convention to search for in a
contract or a scanned form the way there is in this repo's own source.
Chunked prose is exactly the shape embeddings and similarity search exist
for.

**This is not a reversal of "corpus too small."** It is a second, distinct
corpus reaching the size/shape where the deferred technique becomes the
right one, while the first corpus (term candidates) stays exactly where it
was. Both conclusions need to be stated together, or this ADR reads as an
unexplained contradiction of every place that already cites "not yet."

## Decision

**pgvector, scoped to the document-ingestion RAG corpus. Term-similarity
RAG stays deferred, unchanged.**

- **Document RAG (new, this ADR):** document chunks (ADR-0018) get
  embedded and stored in pgvector once Slice 2 of that ADR ships. Slice 1
  (chunk + persist, no embeddings) ships first and is a real, useful
  intermediate state on its own - keyword/metadata search over provenance-
  carrying chunks, before semantic search exists.
- **Term-similarity RAG (unchanged, reaffirmed):** `repo_context.py`'s
  grep-based grounding stays. Term candidates remain too few and too short
  to be worth embedding. This ADR does not touch that code path.

### Why pgvector, not a dedicated vector database

Same reasoning `skills-map.md` already anticipated for this ADR number: at
this corpus size (a handful of documents, low thousands of chunks at most),
a dedicated vector database (Pinecone, Weaviate, Qdrant) is a second
datastore to operate for zero retrieval-quality benefit over an extension
on the Postgres instance this project already runs. Knowing when *not* to
add infrastructure is the point being demonstrated, same argument ADR-0005
makes about streaming.

## Consequences

**Good:**

- Resolves a placeholder five other places in the docs already point at,
  with an answer precise enough to survive being asked "wait, didn't you
  say corpus too small?" in an interview
- One Postgres instance stays the single datastore for both operational
  data and vectors - no new infrastructure to operate
- Document ingestion's Slice 1 (chunk + persist) ships useful and
  demoable before embeddings exist, rather than blocking on them

**Bad:**

- pgvector's HNSW/IVFFlat indexing has real tuning knobs
  (`lists`/`probes`) that only matter at a scale this project won't
  reach - noted, not solved, until volume justifies the work
- Two corpora with different RAG answers is a nuance that has to be
  explained correctly every time this ADR comes up, or it reads as
  inconsistent

## Alternatives considered

**Embed term candidates too, now that pgvector is in.** Rejected: no
corpus-size justification changed for that corpus. Adding embeddings
somewhere because the infrastructure now exists elsewhere is exactly the
instinct ADR-0005 already argues against ("knowing when not to add
infrastructure is the skill being demonstrated").

**A dedicated vector database for document RAG specifically.** Rejected for
the same reason as the general case above - the corpus size doesn't change
which infra is proportionate.

## When I would change this

- If term-candidate volume grows into the hundreds/low-thousands (ADR-0004's
  own "vocabulary plateau" trigger firing at scale), revisit embedding that
  corpus too - grep grounding stops being proportionate at that size.
- If document-chunk volume outgrows what pgvector on the operational
  Postgres instance handles comfortably (rough trigger: index build/query
  latency becomes visible in normal use, not a benchmark), that's the
  signal to evaluate a dedicated vector store - not before.
- If retrieval quality on the document corpus turns out to need hybrid
  search (keyword + vector) rather than vector alone, that's an addition to
  this ADR's Slice 2, not a reason to abandon pgvector.
