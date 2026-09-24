"""Dagster asset: validated knowledge objects, ready to load."""

import dagster as dg
from dagster import AssetExecutionContext

from pipeline_service.candidate import TermCandidate
from pipeline_service.enriched_term import EnrichedTerm
from pipeline_service.validate import validate_batch
from pipeline_service.validate import validate_term


@dg.asset(
    group_name="validate",
    description="Enriched terms that passed every data-quality contract (ADR-0004).",
    dagster_type=dg.Any,  # type: ignore  # variadic tuple; see candidates.py
    ins={"enriched_candidates": dg.AssetIn(dagster_type=dg.Any)},
)
def validated_candidates(
    context: AssetExecutionContext,
    enriched_candidates: tuple[tuple[EnrichedTerm, TermCandidate], ...],
) -> tuple[tuple[EnrichedTerm, TermCandidate], ...]:
    """Validate stage: per-term contracts first (expansion != term,
    Boss-eligible definition length), then a batch-level check across
    everything that passed. A batch failure fails the whole run —
    ADR-0004: "failures block promotion; they do not silently degrade
    the bank" — a broken enricher or duplicate terms means something is
    wrong with this pass, not one bad candidate.
    """
    per_term_errors: list[str] = []
    passed: list[tuple[EnrichedTerm, TermCandidate]] = []

    for term, candidate in enriched_candidates:
        outcome = validate_term(term)
        if outcome.is_valid:
            passed.append((term, candidate))
        else:
            per_term_errors.extend(f"{term.id}: {e}" for e in outcome.errors)

    if per_term_errors:
        context.log.warning(
            "%d candidate(s) failed per-term validation: %s",
            len(per_term_errors),
            "; ".join(per_term_errors),
        )

    batch_outcome = validate_batch(tuple(term for term, _ in passed))
    if not batch_outcome.is_valid:
        raise dg.Failure(
            description="Batch-level validation failed",
            metadata={"errors": dg.MetadataValue.text("\n".join(batch_outcome.errors))},
        )

    context.add_output_metadata(
        {
            "validated_count": len(passed),
            "rejected_count": len(enriched_candidates) - len(passed),
        }
    )
    context.log.info(
        "Validated %d/%d candidates", len(passed), len(enriched_candidates)
    )

    return tuple(passed)
