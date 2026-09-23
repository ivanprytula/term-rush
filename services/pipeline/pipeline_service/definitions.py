"""Dagster entry point: all assets, wired together."""

from __future__ import annotations

import dagster as dg

from pipeline_service.assets.candidates import dependency_manifest_candidates

defs = dg.Definitions(assets=[dependency_manifest_candidates])
