"""Dagster entry point: all assets, wired together.

Two independent pipelines:

- Term candidates: {dependency_manifest_candidates, adr_heading_candidates,
  class_name_candidates} (extract) -> enriched_candidates (enrich) ->
  validated_candidates (validate) -> loaded_candidates (load).
- Document ingestion (ADR-0018): intake_documents (extract) ->
  document_chunks (chunk) -> ingested_chunks (load). No enrich/validate
  stage - chunking is deterministic, nothing here needs an LLM.

Each asset returns its output directly rather than writing a side-effect
file, so Dagster passes data downstream through the ordinary asset-
dependency mechanism (parameter name == upstream asset name) and the
lineage graph reflects the real data flow.
"""

from __future__ import annotations

import dagster as dg

from pipeline_service.assets.candidates import adr_heading_candidates
from pipeline_service.assets.candidates import class_name_candidates
from pipeline_service.assets.candidates import dependency_manifest_candidates
from pipeline_service.assets.enriched import enriched_candidates
from pipeline_service.assets.loaded import loaded_candidates
from pipeline_service.assets.validated import validated_candidates
from pipeline_service.document_ingestion.assets import document_chunks
from pipeline_service.document_ingestion.assets import ingested_chunks
from pipeline_service.document_ingestion.assets import intake_documents

defs = dg.Definitions(
    assets=[
        dependency_manifest_candidates,
        adr_heading_candidates,
        class_name_candidates,
        enriched_candidates,
        validated_candidates,
        loaded_candidates,
        intake_documents,
        document_chunks,
        ingested_chunks,
    ]
)
