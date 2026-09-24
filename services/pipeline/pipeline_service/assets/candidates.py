"""Dagster asset: candidate terms extracted from repo sources.

One asset per source. Returns the candidates themselves (not a file path)
so downstream assets (enrich, validate, load) receive them through
Dagster's IO manager as a normal asset dependency, rather than each stage
re-reading a side-effect file.
"""

from pathlib import Path

import dagster as dg
from dagster import AssetExecutionContext

from pipeline_service.candidate import TermCandidate
from pipeline_service.extractors.adr_headings import extract_adr_headings
from pipeline_service.extractors.dependency_manifest import extract_dependency_manifests

REPO_ROOT = Path(__file__).resolve().parents[4]


@dg.asset(
    group_name="extract",
    description="Candidate terms parsed from every pyproject.toml dependency list.",
    # Dagster's return-annotation type inference can't handle a variadic
    # tuple[X, ...] (it chokes on the Ellipsis) — dagster_type=dg.Any
    # skips inference and passes the value through untyped, same as
    # every other asset in this pipeline that returns a tuple. ty's
    # DagsterType stub doesn't know this special-cased runtime accepts
    # typing.Any directly (it does; see Dagster's own dagster_type docs).
    dagster_type=dg.Any,  # type: ignore
)
def dependency_manifest_candidates(
    context: AssetExecutionContext,
) -> tuple[TermCandidate, ...]:
    """Extract stage for the dependency-manifest source (ADR-0004,
    highest-confidence source: structured, machine-parseable).
    """
    candidates = extract_dependency_manifests(REPO_ROOT)

    context.add_output_metadata(
        {
            "candidate_count": len(candidates),
            "preview": dg.MetadataValue.md(
                "\n".join(f"- `{c.name}`" for c in candidates[:20])
            ),
        }
    )
    context.log.info("Extracted %d candidates", len(candidates))

    return candidates


@dg.asset(
    group_name="extract",
    description="Candidate terms parsed from backtick-quoted identifiers in ADR headings.",
    dagster_type=dg.Any,  # type: ignore  # variadic tuple; see above
)
def adr_heading_candidates(
    context: AssetExecutionContext,
) -> tuple[TermCandidate, ...]:
    """Extract stage for the ADR-heading source (ADR-0004, Medium-
    confidence source: curated prose, human-written).
    """
    candidates = extract_adr_headings(REPO_ROOT)

    context.add_output_metadata(
        {
            "candidate_count": len(candidates),
            "preview": dg.MetadataValue.md(
                "\n".join(f"- `{c.name}`" for c in candidates[:20])
            ),
        }
    )
    context.log.info("Extracted %d candidates", len(candidates))

    return candidates
