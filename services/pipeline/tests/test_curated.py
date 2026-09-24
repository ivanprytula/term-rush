"""Tests for the curated-source loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.curated import DEFAULT_CURATED_TERMS_PATH
from pipeline_service.curated import load_curated_terms
from pipeline_service.enriched_term import EnrichedTerm


def test_load_curated_terms_parses_the_real_seed_file() -> None:
    """End-to-end against the actual repo's curated_terms.yaml."""
    pairs = load_curated_terms()

    assert len(pairs) > 0
    names = {candidate.name for _, candidate in pairs}
    assert "GIL" in names


def test_load_curated_terms_sets_provenance() -> None:
    pairs = load_curated_terms()

    for term, candidate in pairs:
        assert isinstance(term, EnrichedTerm)
        assert candidate.source_type == SourceType.CURATED
        assert candidate.confidence == Confidence.CURATED
        assert candidate.source_file == str(DEFAULT_CURATED_TERMS_PATH)
        assert candidate.name == term.term


def test_load_curated_terms_from_a_custom_path(tmp_path: Path) -> None:
    seed = tmp_path / "custom.yaml"
    seed.write_text(
        "- id: example-term\n"
        "  term: Example Term\n"
        "  expansion: Example Term\n"
        "  definitions: ['A definition.']\n"
        "  categories: [theory]\n"
        "  difficulty: 2\n"
    )

    pairs = load_curated_terms(seed)

    assert len(pairs) == 1
    term, candidate = pairs[0]
    assert term.id == "example-term"
    assert candidate.source_file == str(seed)


def test_load_curated_terms_empty_file_yields_no_pairs(tmp_path: Path) -> None:
    seed = tmp_path / "empty.yaml"
    seed.write_text("")

    pairs = load_curated_terms(seed)

    assert pairs == ()


def test_load_curated_terms_raises_on_a_malformed_entry(tmp_path: Path) -> None:
    seed = tmp_path / "malformed.yaml"
    seed.write_text(
        "- id: bad\n"
        "  term: Bad\n"
        "  expansion: Bad\n"
        "  definitions: []\n"  # violates EnrichedTerm's min_length=1
        "  categories: [theory]\n"
        "  difficulty: 2\n"
    )

    with pytest.raises(Exception):  # noqa: B017 - pydantic's own ValidationError
        load_curated_terms(seed)
