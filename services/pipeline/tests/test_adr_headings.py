"""Tests for the ADR-heading extractor."""

from __future__ import annotations

from pathlib import Path

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.extractors.adr_headings import extract_adr_headings
from pipeline_service.extractors.adr_headings import extract_from_adr
from pipeline_service.extractors.adr_headings import find_adr_files

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_find_adr_files_only_docs_adr(tmp_path: Path) -> None:
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-foo.md").write_text("# ADR\n")
    (tmp_path / "README.md").write_text("# not an adr\n")

    found = find_adr_files(tmp_path)

    assert found == (adr_dir / "0001-foo.md",)


def test_extract_from_adr_takes_backticked_identifiers_in_h3_headings(
    tmp_path: Path,
) -> None:
    adr = tmp_path / "0099-example.md"
    adr.write_text(
        "# ADR-0099: Example\n\n"
        "## Decision\n\n"
        "### One `RoundOver` exception, not one per mode\n\n"
        "body text\n"
    )

    candidates = extract_from_adr(adr)

    names = {c.name for c in candidates}
    assert names == {"RoundOver"}


def test_extract_from_adr_skips_h2_headings(tmp_path: Path) -> None:
    adr = tmp_path / "0099-example.md"
    adr.write_text("## `NotExtracted` at H2\n\n### `Extracted` at H3\n")

    candidates = extract_from_adr(adr)

    names = {c.name for c in candidates}
    assert names == {"Extracted"}


def test_extract_from_adr_filters_url_fragments_and_query_strings(
    tmp_path: Path,
) -> None:
    adr = tmp_path / "0099-example.md"
    adr.write_text(
        "### Readiness: consumer health degrades `/ready`, never fails it\n\n"
        "### REST response embedding (`?embed=categories,term`)\n\n"
        "### One `RoundOver` exception\n"
    )

    candidates = extract_from_adr(adr)

    names = {c.name for c in candidates}
    assert names == {"RoundOver"}


def test_extract_from_adr_skips_headings_with_no_backticks(tmp_path: Path) -> None:
    adr = tmp_path / "0099-example.md"
    adr.write_text("### Why this is the right shape for the project\n")

    candidates = extract_from_adr(adr)

    assert candidates == ()


def test_extract_from_adr_dedupes_within_one_file(tmp_path: Path) -> None:
    adr = tmp_path / "0099-example.md"
    adr.write_text(
        "### One `RoundOver` exception, not one per mode\n\n"
        "### Another use of `RoundOver` here\n"
    )

    candidates = extract_from_adr(adr)

    assert len(candidates) == 1


def test_extract_from_adr_sets_provenance(tmp_path: Path) -> None:
    adr = tmp_path / "0099-example.md"
    adr.write_text("### One `RoundOver` exception\n")

    candidates = extract_from_adr(adr)

    assert candidates
    for candidate in candidates:
        assert candidate.source_type == SourceType.ADR_HEADING
        assert candidate.confidence == Confidence.MEDIUM
        assert candidate.source_file == str(adr)


def test_extract_adr_headings_covers_the_real_repo() -> None:
    """End-to-end against the actual repo's ADRs: proves the extractor
    produces real vocabulary, not just toy fixtures.
    """
    candidates = extract_adr_headings(REPO_ROOT)

    names = {c.name for c in candidates}
    assert "RoundOver" in names
    assert "ANTHROPIC_API_KEY" in names
    assert "bff" in names
    # URL fragments and query strings must never surface as vocabulary.
    assert "/ready" not in names


def test_extract_adr_headings_deduplicates_across_files() -> None:
    """`ANTHROPIC_API_KEY` is backticked in more than one ADR; it must
    yield one candidate, not one per occurrence.
    """
    candidates = extract_adr_headings(REPO_ROOT)

    names = [c.name for c in candidates]
    assert names.count("ANTHROPIC_API_KEY") == 1
