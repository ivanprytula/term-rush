"""Dagster entry point: all assets, wired together.

The pipeline graph: {dependency_manifest_candidates, adr_heading_candidates,
class_name_candidates} (extract) -> enriched_candidates (enrich) ->
validated_candidates (validate) -> loaded_candidates (load). Each asset
returns its output directly rather than writing a side-effect file, so
Dagster passes data downstream through the ordinary asset-dependency
mechanism (parameter name == upstream asset name) and the lineage graph
reflects the real data flow.
"""

from __future__ import annotations

import dagster as dg

from pipeline_service.assets.candidates import adr_heading_candidates
from pipeline_service.assets.candidates import class_name_candidates
from pipeline_service.assets.candidates import dependency_manifest_candidates
from pipeline_service.assets.enriched import enriched_candidates
from pipeline_service.assets.loaded import loaded_candidates
from pipeline_service.assets.validated import validated_candidates

defs = dg.Definitions(
    assets=[
        dependency_manifest_candidates,
        adr_heading_candidates,
        class_name_candidates,
        enriched_candidates,
        validated_candidates,
        loaded_candidates,
    ]
)
