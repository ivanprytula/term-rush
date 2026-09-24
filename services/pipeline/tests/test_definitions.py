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

from pipeline_service.assets.candidates import adr_heading_candidates
from pipeline_service.assets.candidates import class_name_candidates
from pipeline_service.assets.candidates import dependency_manifest_candidates
from pipeline_service.assets.enriched import enriched_candidates
from pipeline_service.assets.loaded import loaded_candidates
from pipeline_service.assets.validated import validated_candidates
from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.candidate import TermCandidate
from pipeline_service.definitions import defs
from pipeline_service.enrich import AnthropicEnricher
from pipeline_service.enriched_term import EnrichedTerm


def test_definitions_resolve_every_asset() -> None:
    graph = defs.resolve_asset_graph()
    keys = {k.to_user_string() for k in graph.get_all_asset_keys()}

    assert keys == {
        "dependency_manifest_candidates",
        "adr_heading_candidates",
        "class_name_candidates",
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


def test_adr_heading_asset_materializes_real_candidates() -> None:
    result = dg.materialize([adr_heading_candidates])

    assert result.success
    candidates = result.output_for_node("adr_heading_candidates")
    assert len(candidates) > 0
    assert all(isinstance(c, TermCandidate) for c in candidates)


def test_class_name_asset_materializes_real_candidates() -> None:
    result = dg.materialize([class_name_candidates])

    assert result.success
    candidates = result.output_for_node("class_name_candidates")
    assert len(candidates) > 0
    assert all(isinstance(c, TermCandidate) for c in candidates)


def _materialize_enrich_dedup(
    monkeypatch: pytest.MonkeyPatch,
    manifest_candidates: tuple[TermCandidate, ...],
    adr_candidates: tuple[TermCandidate, ...],
    class_candidates: tuple[TermCandidate, ...] = (),
) -> list[TermCandidate]:
    """Materialize enriched_candidates against fake upstream assets,
    recording which TermCandidate each enrich() call received.
    """

    @dg.asset(dagster_type=dg.Any, name="dependency_manifest_candidates")  # type: ignore
    def fake_manifest_candidates() -> tuple[TermCandidate, ...]:
        return manifest_candidates

    @dg.asset(dagster_type=dg.Any, name="adr_heading_candidates")  # type: ignore
    def fake_adr_candidates() -> tuple[TermCandidate, ...]:
        return adr_candidates

    @dg.asset(dagster_type=dg.Any, name="class_name_candidates")  # type: ignore
    def fake_class_candidates() -> tuple[TermCandidate, ...]:
        return class_candidates

    enrich_calls: list[TermCandidate] = []

    async def _fake_enrich(self, candidate, snippets):  # noqa: ANN001, ANN202, ARG001
        enrich_calls.append(candidate)
        return EnrichedTerm(
            id="x",
            term=candidate.name,
            expansion=candidate.name,
            definitions=("A definition.",),
            categories=("theory",),
            difficulty=1,
        )

    monkeypatch.setattr(AnthropicEnricher, "enrich", _fake_enrich)

    result = dg.materialize(
        [
            fake_manifest_candidates,
            fake_adr_candidates,
            fake_class_candidates,
            enriched_candidates,
        ]
    )
    assert result.success
    return enrich_calls


def test_enrich_asset_dedupes_a_term_named_by_two_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`fastapi` extracted by both sources must enrich once."""
    manifest_candidate = TermCandidate(
        name="fastapi",
        source_type=SourceType.DEPENDENCY_MANIFEST,
        source_file="pyproject.toml",
        confidence=Confidence.HIGH,
    )
    adr_candidate = TermCandidate(
        name="FastAPI",  # differs only by case/normalization from the above
        source_type=SourceType.ADR_HEADING,
        source_file="docs/adr/0003.md",
        confidence=Confidence.MEDIUM,
    )

    enrich_calls = _materialize_enrich_dedup(
        monkeypatch, (manifest_candidate,), (adr_candidate,)
    )

    assert len(enrich_calls) == 1


def test_enrich_asset_dedup_keeps_higher_confidence_even_when_seen_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The winner is decided by confidence rank, not extraction/merge
    order: a HIGH-confidence candidate wins even when the asset that
    yields it is positioned after the LOW-confidence one in the params
    the enrich asset receives.

    low_confidence is passed as the FIRST tuple (dependency_manifest_
    candidates param) and high_confidence as the SECOND (adr_heading_
    candidates) - inverted from the "expected" source pairing, so a
    merge-order-based dedup would keep low_confidence. Rank-based dedup
    must still win with high_confidence regardless.
    """
    low_confidence = TermCandidate(
        name="fastapi",
        source_type=SourceType.ADR_HEADING,
        source_file="docs/adr/0003.md",
        confidence=Confidence.LOW,
    )
    high_confidence = TermCandidate(
        name="FastAPI",
        source_type=SourceType.DEPENDENCY_MANIFEST,
        source_file="pyproject.toml",
        confidence=Confidence.HIGH,
    )

    enrich_calls = _materialize_enrich_dedup(
        monkeypatch, (low_confidence,), (high_confidence,)
    )

    assert len(enrich_calls) == 1
    assert enrich_calls[0] == high_confidence


def test_enrich_asset_includes_the_class_name_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A candidate that only the class-name source yields must still
    reach enrich - proves class_name_candidates is actually wired into
    the merge, not just declared as an unused asset dependency.
    """
    class_candidate = TermCandidate(
        name="UnitOfWork",
        source_type=SourceType.CLASS_NAME,
        source_file="ports.py",
        confidence=Confidence.MEDIUM,
    )

    enrich_calls = _materialize_enrich_dedup(monkeypatch, (), (), (class_candidate,))

    assert enrich_calls == [class_candidate]


def test_enrich_asset_dedup_spans_all_three_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same term named by all three sources still enriches once,
    keeping the highest-confidence candidate.
    """
    low_confidence = TermCandidate(
        name="unitofwork",
        source_type=SourceType.CLASS_NAME,
        source_file="ports.py",
        confidence=Confidence.MEDIUM,
    )
    lower_confidence = TermCandidate(
        name="UnitOfWork",
        source_type=SourceType.ADR_HEADING,
        source_file="docs/adr/0003.md",
        confidence=Confidence.LOW,
    )
    highest_confidence = TermCandidate(
        name="Unit-Of-Work",
        source_type=SourceType.DEPENDENCY_MANIFEST,
        source_file="pyproject.toml",
        confidence=Confidence.HIGH,
    )

    enrich_calls = _materialize_enrich_dedup(
        monkeypatch,
        (highest_confidence,),
        (lower_confidence,),
        (low_confidence,),
    )

    assert enrich_calls == [highest_confidence]


def test_validate_asset_rejects_a_term_that_fails_a_contract() -> None:
    bad_term = EnrichedTerm(
        id="bad",
        term="bad",
        expansion="Bad Example",
        definitions=("too short.",),  # < 40 chars, and Boss-eligible below
        categories=("theory",),
        difficulty=4,
        examples=("an example",),  # difficulty>=3 + examples = Boss-eligible
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
