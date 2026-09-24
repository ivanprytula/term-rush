"""Validate: the data-quality contracts an EnrichedTerm must pass before
it can reach load (ADR-0004). Pure functions — no LLM, no network.

Contracts covered here:
- expansion non-empty (enforced by EnrichedTerm's own min_length, not
  re-checked here — the "must differ from term" clause was dropped:
  a proper noun like `dagster` has no acronym to expand, ADR-0004 Resolution)
- at least one definition, >=40 chars for anything Boss-eligible
  (difficulty >= MODERATE and has examples)
- no duplicate terms after normalization, within one batch
- difficulty distribution stays sane, across one batch
- provenance is present (structural: source_type/source_file/confidence
  are non-empty fields on TermCandidate, enforced by that model already)

Deferred (need the live term bank, not just this batch — see this
session's earlier scoping decision):
- prerequisites/related resolve to terms that exist
The prerequisite DAG check is still built here (dag_has_cycle) since a
cycle is detectable from a batch alone, even though no source produces
prerequisites yet.
"""

from __future__ import annotations

from pydantic import BaseModel

from pipeline_service.enriched_term import EnrichedTerm

BOSS_ELIGIBLE_MIN_DIFFICULTY = 3  # matches content-service's Difficulty.MODERATE
BOSS_ELIGIBLE_MIN_DEFINITION_LEN = 40  # matches content-service's constants.py
MAX_EXPERT_FRACTION = 0.5  # an all-EXPERT batch is a broken enricher, not a hard bank


class ValidationOutcome(BaseModel):
    """Typed pass/fail — the caller learns exactly what failed, not just
    that something did.
    """

    is_valid: bool
    errors: tuple[str, ...] = ()

    @staticmethod
    def ok() -> ValidationOutcome:
        return ValidationOutcome(is_valid=True)

    @staticmethod
    def fail(*errors: str) -> ValidationOutcome:
        return ValidationOutcome(is_valid=False, errors=errors)


def _normalized(term_name: str) -> str:
    """TCP/IP and TCP IP collapse to the same key: lowercase, non-
    alphanumeric stripped."""
    return "".join(c for c in term_name.lower() if c.isalnum())


def validate_term(term: EnrichedTerm) -> ValidationOutcome:
    """Per-term contracts: definition length for anything Boss-eligible.

    expansion non-empty is enforced by EnrichedTerm's own field
    constraint, not re-checked here.
    """
    errors: list[str] = []

    primary_definition = term.definitions[0] if term.definitions else ""
    is_boss_eligible = term.difficulty >= BOSS_ELIGIBLE_MIN_DIFFICULTY and bool(
        term.examples
    )
    if is_boss_eligible and len(primary_definition) < BOSS_ELIGIBLE_MIN_DEFINITION_LEN:
        errors.append(
            f"primary definition is {len(primary_definition)} chars, needs "
            f">={BOSS_ELIGIBLE_MIN_DEFINITION_LEN} for a Boss-eligible term "
            f"(difficulty={term.difficulty}, has examples)"
        )

    return ValidationOutcome.fail(*errors) if errors else ValidationOutcome.ok()


def validate_batch(terms: tuple[EnrichedTerm, ...]) -> ValidationOutcome:
    """Batch-level contracts: no duplicate terms after normalization, and
    the difficulty distribution isn't suspiciously skewed.
    """
    errors: list[str] = []

    seen: dict[str, str] = {}
    for term in terms:
        key = _normalized(term.term)
        if key in seen:
            errors.append(
                f"duplicate term after normalization: {term.term!r} and "
                f"{seen[key]!r} both normalize to {key!r}"
            )
        else:
            seen[key] = term.term

    if terms:
        expert_count = sum(1 for t in terms if t.difficulty == 5)
        if expert_count / len(terms) > MAX_EXPERT_FRACTION:
            errors.append(
                f"{expert_count}/{len(terms)} terms are difficulty=5 (EXPERT) "
                f"— exceeds {MAX_EXPERT_FRACTION:.0%}, likely a broken enricher"
            )

    return ValidationOutcome.fail(*errors) if errors else ValidationOutcome.ok()


def dag_has_cycle(prerequisites: dict[str, tuple[str, ...]]) -> tuple[str, ...] | None:
    """Detect a cycle in the prerequisite graph via DFS with a recursion
    stack. `prerequisites` maps term_id -> the term_ids it requires.
    Returns the cycle's term_ids in order if one exists, else None.

    A term cannot transitively require itself — that's how a learning
    path silently becomes unsatisfiable (ADR-0004).
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(prerequisites, WHITE)
    path: list[str] = []

    def visit(node: str) -> tuple[str, ...] | None:
        color[node] = GRAY
        path.append(node)
        for neighbor in prerequisites.get(node, ()):
            if neighbor not in color:
                continue  # references a term outside this graph; not this check's job
            if color[neighbor] == GRAY:
                cycle_start = path.index(neighbor)
                return tuple(path[cycle_start:])
            if color[neighbor] == WHITE:
                found = visit(neighbor)
                if found is not None:
                    return found
        path.pop()
        color[node] = BLACK
        return None

    for node in prerequisites:
        if color[node] == WHITE:
            found = visit(node)
            if found is not None:
                return found
    return None
