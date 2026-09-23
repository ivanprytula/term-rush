"""Dagster asset: candidate terms extracted from repo sources.

One asset per source today (dependency manifests). Materializing writes
candidates to a JSON file under the Dagster instance's storage — a
landing zone, not the live term bank; load/review (ADR-0004) is a later
stage that reads this asset's output and decides what gets promoted.
"""

import json
from pathlib import Path

import dagster as dg
from dagster import AssetExecutionContext

from pipeline_service.extractors.dependency_manifest import extract_dependency_manifests

REPO_ROOT = Path(__file__).resolve().parents[4]


@dg.asset(
    group_name="extract",
    description="Candidate terms parsed from every pyproject.toml dependency list.",
)
def dependency_manifest_candidates(
    context: AssetExecutionContext,
) -> dg.MaterializeResult:
    """Extract stage for the dependency-manifest source (ADR-0004,
    highest-confidence source: structured, machine-parseable).
    """
    candidates = extract_dependency_manifests(REPO_ROOT)

    output_path = (
        Path(context.instance.storage_directory())
        / "dependency_manifest_candidates.json"
    )
    output_path.write_text(
        json.dumps([c.model_dump(mode="json") for c in candidates], indent=2)
    )

    context.log.info("Extracted %d candidates -> %s", len(candidates), output_path)

    return dg.MaterializeResult(
        metadata={
            "candidate_count": len(candidates),
            "output_path": str(output_path),
            "preview": dg.MetadataValue.md(
                "\n".join(f"- `{c.name}`" for c in candidates[:20])
            ),
        }
    )
