"""get_unit_of_work tests: the grade cache must be a shared instance across
requests, not reconstructed per call (a UnitOfWork is built fresh every
request, so a cache built inside it would never see a second lookup)."""

from __future__ import annotations

import pytest

from game_service.api.dependencies import get_unit_of_work
from game_service.domain.outcome import GradeOutcome
from game_service.domain.outcome import MatchedVia
from game_service.domain.outcome import RubricBreakdown
from game_service.domain.outcome import Verdict


def _outcome() -> GradeOutcome:
    return GradeOutcome(
        verdict=Verdict.CORRECT,
        matched_via=MatchedVia.EXACT,
        confidence=1.0,
        feedback="Correct.",
        rubric=RubricBreakdown(expansion=30, concept=40, purpose=20, example=10),
    )


@pytest.mark.asyncio
async def test_grade_cache_is_shared_across_separate_unit_of_work_instances() -> None:
    """Two separate get_unit_of_work() calls (i.e. two separate requests)
    must see the same grade cache, or a put() in one request is invisible
    to a get() in the next — the bug this test pins against."""
    gen1 = get_unit_of_work()
    uow1 = await anext(gen1)
    await uow1.grade_cache.put("uow", "hash-1", _outcome())
    with pytest.raises(StopAsyncIteration):
        await anext(gen1)

    gen2 = get_unit_of_work()
    uow2 = await anext(gen2)
    cached = await uow2.grade_cache.get("uow", "hash-1")
    with pytest.raises(StopAsyncIteration):
        await anext(gen2)

    assert cached is not None
    assert cached.verdict == Verdict.CORRECT
