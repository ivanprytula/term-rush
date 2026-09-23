"""Tests that the Dagster asset graph itself is wired correctly.

Complements the per-stage unit tests: those prove each function is
correct in isolation, these prove Dagster can actually load the graph
and pass data between assets through its real IO manager (the class of
bug hit while building this — dagster_type=Any for variadic tuples,
parameter names matching upstream asset names — isn't visible from
testing the stage functions directly).
"""

from __future__ import annotations

import dagster as dg
import pytest

from pipeline_service.assets.candidates import dependency_manifest_candidates
from pipeline_service.assets.loaded import loaded_candidates
from pipeline_service.assets.validated import validated_candidates
from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.candidate import TermCandidate
from pipeline_service.definitions import defs
from pipeline_service.enriched_term import EnrichedTerm


def test_definitions_resolve_every_asset() -> None:
    graph = defs.resolve_asset_graph()
    keys = {k.to_user_string() for k in graph.get_all_asset_keys()}

    assert keys == {
        "dependency_manifest_candidates",
        "enriched_candidates",
        "validated_candidates",
        "loaded_candidates",
    }


def test_extract_asset_materializes_real_candidates() -> None:
    result = dg.materialize([dependency_manifest_candidates])

    assert result.success
    candidates = result.output_for_node("dependency_manifest_candidates")
    assert len(candidates) > 0
    assert all(isinstance(c, TermCandidate) for c in candidates)


def test_validate_asset_rejects_a_term_that_fails_a_contract() -> None:
    bad_term = EnrichedTerm(
        id="bad",
        term="bad",
        expansion="bad",  # same as term - fails validate_term
        definitions=("A definition.",),
        categories=("theory",),
        difficulty=2,
    )
    candidate = TermCandidate(
        name="bad",
        source_type=SourceType.DEPENDENCY_MANIFEST,
        source_file="x",
        confidence=Confidence.HIGH,
    )

    @dg.asset(dagster_type=dg.Any)  # type: ignore
    def enriched_candidates() -> tuple[tuple[EnrichedTerm, TermCandidate], ...]:
        return ((bad_term, candidate),)

    result = dg.materialize([enriched_candidates, validated_candidates])

    assert result.success
    assert result.output_for_node("validated_candidates") == ()


def test_validate_then_load_chain_submits_the_valid_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The full validate -> load handoff, with load's HTTP call stubbed
    (no real content-service needed) — proves the asset graph passes
    data correctly across two hops, not just one.
    """
    good_term = EnrichedTerm(
        id="good",
        term="good-term",
        expansion="A Good Term",
        definitions=("A definition.",),
        categories=("theory",),
        difficulty=2,
    )
    candidate = TermCandidate(
        name="good-term",
        source_type=SourceType.DEPENDENCY_MANIFEST,
        source_file="x",
        confidence=Confidence.HIGH,
    )

    @dg.asset(dagster_type=dg.Any)  # type: ignore
    def enriched_candidates() -> tuple[tuple[EnrichedTerm, TermCandidate], ...]:
        return ((good_term, candidate),)

    async def _fake_submit_for_review(_client, _url, term, _candidate) -> int:
        assert term.id == "good"
        return 99

    monkeypatch.setattr(
        "pipeline_service.assets.loaded.submit_for_review", _fake_submit_for_review
    )

    result = dg.materialize(
        [enriched_candidates, validated_candidates, loaded_candidates]
    )

    assert result.success
    assert result.output_for_node("loaded_candidates") == (99,)
