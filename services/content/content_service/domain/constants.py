"""Domain constants: term bounds.

Single source of truth for content-service's magic numbers. Changes here
propagate to validation, schemas, and tests automatically.
"""

TERM_ID_MIN_LEN = 1
TERM_ID_MAX_LEN = 64
TERM_MIN_LEN = 1
TERM_MAX_LEN = 64
TERM_SLUG_MIN_LEN = 1
TERM_SLUG_MAX_LEN = 32
TERM_EXPANSION_MIN_LEN = 1
TERM_EXPANSION_MAX_LEN = 256
TERM_DEFINITION_MIN_LEN = 1
TERM_DEFINITION_MAX_LEN = 1024
TERM_PRIMARY_DEFINITION_MIN_LEN = 40  # Boss-eligible terms require ≥40 chars

# Document chunks (ADR-0018): bound generously above pipeline-service's own
# CHUNK_SIZE_CHARS (1000) — this is a sanity ceiling at content-service's
# boundary, not the chunking policy itself, which pipeline-service owns.
DOCUMENT_CHUNK_MAX_LEN = 4096
DOCUMENT_CHUNK_SOURCE_FILE_MAX_LEN = 512

# ADR-0012 Slice 2: all-MiniLM-L6-v2's output size (served via ONNX/
# fastembed — see infrastructure/onnx_embedder.py). Changing embedding
# models means changing this and re-embedding every row — there is no
# migration path between differently-sized vector columns.
DOCUMENT_CHUNK_EMBEDDING_DIM = 384

# Batch size for EmbedDocumentChunks — bounds one pass over the backlog so
# it runs as a repeatable, schedulable job rather than an unbounded scan.
EMBED_BATCH_SIZE = 64

# Default number of chunks SearchChunksBySimilarity returns — a RAG prompt
# has a token budget, so "give me everything similar" isn't the right
# default; a caller who genuinely needs more can ask for it explicitly.
SEARCH_DEFAULT_TOP_K = 5
