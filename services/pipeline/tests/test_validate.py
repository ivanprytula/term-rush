"""Tests for the validate stage's data-quality contracts (ADR-0004)."""

from __future__ import annotations

from pipeline_service.enriched_term import EnrichedTerm
from pipeline_service.validate import dag_has_cycle
from pipeline_service.validate import validate_batch
from pipeline_service.validate import validate_term


def _term(
    term_id: str = "fastapi",
    term: str | None = None,
    expansion: str = "A Python web framework",
    definitions: tuple[str, ...] = ("A Python web framework.",),
    difficulty: int = 3,
    examples: tuple[str, ...] = (),
) -> EnrichedTerm:
    return EnrichedTerm(
        id=term_id,
        term=term if term is not None else term_id,
        expansion=expansion,
        definitions=definitions,
        categories=("web-frameworks",),
        difficulty=difficulty,
        examples=examples,
    )


def test_validate_term_passes_a_well_formed_term() -> None:
    outcome = validate_term(_term())

    assert outcome.is_valid
    assert outcome.errors == ()


def test_validate_term_rejects_expansion_equal_to_term() -> None:
    outcome = validate_term(_term(term="fastapi", expansion="fastapi"))

    assert not outcome.is_valid
    assert any("differ from term" in e for e in outcome.errors)


def test_validate_term_rejects_expansion_equal_to_term_case_insensitive() -> None:
    outcome = validate_term(_term(term="FastAPI", expansion="fastapi"))

    assert not outcome.is_valid


def test_validate_term_rejects_short_definition_when_boss_eligible() -> None:
    outcome = validate_term(
        _term(difficulty=4, examples=("an example",), definitions=("too short.",))
    )

    assert not outcome.is_valid
    assert any("Boss-eligible" in e for e in outcome.errors)


def test_validate_term_allows_short_definition_when_not_boss_eligible() -> None:
    # difficulty below MODERATE threshold, so Boss-eligibility never applies.
    outcome = validate_term(_term(difficulty=1, definitions=("short.",)))

    assert outcome.is_valid


def test_validate_term_allows_short_definition_without_examples() -> None:
    # Boss-eligible requires examples too; none here.
    outcome = validate_term(_term(difficulty=4, examples=(), definitions=("short.",)))

    assert outcome.is_valid


def test_validate_batch_passes_distinct_terms() -> None:
    outcome = validate_batch((_term(term_id="fastapi"), _term(term_id="sqlalchemy")))

    assert outcome.is_valid


def test_validate_batch_rejects_duplicate_terms_after_normalization() -> None:
    outcome = validate_batch(
        (
            _term(term_id="tcp-ip", term="TCP/IP"),
            _term(term_id="tcpip", term="TCP IP"),
        )
    )

    assert not outcome.is_valid
    assert any("duplicate term" in e for e in outcome.errors)


def test_validate_batch_rejects_when_over_half_are_expert_difficulty() -> None:
    terms = tuple(_term(term_id=f"t{i}", difficulty=5) for i in range(3)) + (
        _term(term_id="t4", difficulty=2),
    )

    outcome = validate_batch(terms)

    assert not outcome.is_valid
    assert any("EXPERT" in e for e in outcome.errors)


def test_validate_batch_allows_a_minority_of_expert_terms() -> None:
    terms = (_term(term_id="t1", difficulty=5), _term(term_id="t2", difficulty=2))

    outcome = validate_batch(terms)

    assert outcome.is_valid


def test_validate_batch_of_empty_tuple_is_valid() -> None:
    assert validate_batch(()).is_valid


def test_dag_has_cycle_detects_a_direct_cycle() -> None:
    graph: dict[str, tuple[str, ...]] = {"a": ("b",), "b": ("a",)}

    cycle = dag_has_cycle(graph)

    assert cycle is not None
    assert set(cycle) == {"a", "b"}


def test_dag_has_cycle_detects_a_transitive_cycle() -> None:
    graph: dict[str, tuple[str, ...]] = {"a": ("b",), "b": ("c",), "c": ("a",)}

    cycle = dag_has_cycle(graph)

    assert cycle is not None
    assert set(cycle) == {"a", "b", "c"}


def test_dag_has_cycle_returns_none_for_a_valid_dag() -> None:
    graph = {"a": ("b", "c"), "b": ("c",), "c": ()}

    assert dag_has_cycle(graph) is None


def test_dag_has_cycle_ignores_references_outside_the_graph() -> None:
    # "b" requires "external", which isn't a key in the graph at all -
    # not this check's job (deferred to an existence check against the
    # live term bank, per this session's scoping decision).
    graph: dict[str, tuple[str, ...]] = {"a": ("b",), "b": ("external",)}

    assert dag_has_cycle(graph) is None


def test_dag_has_cycle_handles_an_empty_graph() -> None:
    assert dag_has_cycle({}) is None


def test_dag_has_cycle_handles_self_reference() -> None:
    graph: dict[str, tuple[str, ...]] = {"a": ("a",)}

    cycle = dag_has_cycle(graph)

    assert cycle == ("a",)
