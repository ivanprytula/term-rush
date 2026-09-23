"""Application use case tests."""

from __future__ import annotations

import pytest

from content_service.application.use_cases import ApproveReviewCandidate
from content_service.application.use_cases import GetRandomTerm
from content_service.application.use_cases import GetTermById
from content_service.application.use_cases import ListCategories
from content_service.application.use_cases import ListReviewCandidates
from content_service.application.use_cases import PublishTerm
from content_service.application.use_cases import RejectReviewCandidate
from content_service.application.use_cases import SubmitReviewCandidate
from content_service.domain.review import ReviewCandidateNotPending
from content_service.domain.review import ReviewStatus
from content_service.domain.term import Category
from content_service.domain.term import Term
from content_service.infrastructure.memory import InMemoryEventPublisher
from content_service.infrastructure.memory import InMemoryUnitOfWork


@pytest.fixture
def term() -> Term:
    return Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("Pattern that groups related changes into one unit.",),
        categories=(Category(slug="architecture"),),
    )


@pytest.fixture
def uow(term: Term) -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork(terms={term.id: term})


@pytest.mark.asyncio
async def test_get_term_by_id_returns_the_term(
    uow: InMemoryUnitOfWork, term: Term
) -> None:
    use_case = GetTermById(uow)

    assert await use_case.execute(term.id) == term


@pytest.mark.asyncio
async def test_get_term_by_id_raises_when_missing(uow: InMemoryUnitOfWork) -> None:
    use_case = GetTermById(uow)

    with pytest.raises(ValueError, match="not found"):
        await use_case.execute("nonexistent")


@pytest.mark.asyncio
async def test_get_random_term_returns_the_only_term(
    uow: InMemoryUnitOfWork, term: Term
) -> None:
    use_case = GetRandomTerm(uow)

    assert await use_case.execute() == term


@pytest.mark.asyncio
async def test_get_random_term_raises_when_bank_is_empty() -> None:
    use_case = GetRandomTerm(InMemoryUnitOfWork())

    with pytest.raises(ValueError, match="No terms available"):
        await use_case.execute()


@pytest.mark.asyncio
async def test_get_random_term_avoids_excluded_ids(term: Term) -> None:
    other = term.model_copy(update={"id": "cqrs", "term": "CQRS"})
    uow = InMemoryUnitOfWork(terms={term.id: term, other.id: other})
    use_case = GetRandomTerm(uow)

    result = await use_case.execute(frozenset({term.id}))

    assert result.id == other.id


@pytest.mark.asyncio
async def test_get_random_term_falls_back_once_all_ids_excluded(
    uow: InMemoryUnitOfWork, term: Term
) -> None:
    use_case = GetRandomTerm(uow)

    result = await use_case.execute(frozenset({term.id}))

    assert result == term


@pytest.mark.asyncio
async def test_get_random_term_scopes_to_category(term: Term) -> None:
    other = term.model_copy(
        update={
            "id": "lambda",
            "term": "lambda",
            "categories": (Category(slug="python-keywords"),),
        }
    )
    uow = InMemoryUnitOfWork(terms={term.id: term, other.id: other})
    use_case = GetRandomTerm(uow)

    result = await use_case.execute(category="python-keywords")

    assert result == other


@pytest.mark.asyncio
async def test_get_random_term_raises_when_category_has_no_terms(
    uow: InMemoryUnitOfWork,
) -> None:
    use_case = GetRandomTerm(uow)

    with pytest.raises(ValueError, match="No terms available"):
        await use_case.execute(category="nonexistent-category")


@pytest.mark.asyncio
async def test_list_categories_returns_every_distinct_slug(term: Term) -> None:
    other = term.model_copy(
        update={"id": "lambda", "categories": (Category(slug="python-keywords"),)}
    )
    uow = InMemoryUnitOfWork(terms={term.id: term, other.id: other})
    use_case = ListCategories(uow)

    assert await use_case.execute() == ("architecture", "python-keywords")


@pytest.mark.asyncio
async def test_publish_term_upserts_and_returns_it() -> None:
    uow = InMemoryUnitOfWork()
    new_term = Term(
        id="fsm",
        term="FSM",
        expansion="Finite State Machine",
        definitions=("A model with a finite number of states and transitions.",),
        categories=(Category(slug="theory"),),
    )
    use_case = PublishTerm(uow)

    result = await use_case.execute(new_term)

    assert result == new_term
    assert await uow.terms.by_id("fsm") == new_term


@pytest.mark.asyncio
async def test_publish_term_publishes_term_published_event() -> None:
    uow = InMemoryUnitOfWork()
    term = Term(
        id="fsm",
        term="FSM",
        expansion="Finite State Machine",
        definitions=("A model with a finite number of states and transitions.",),
        categories=(Category(slug="theory"),),
    )
    use_case = PublishTerm(uow)

    await use_case.execute(term)

    events = uow.events
    assert isinstance(events, InMemoryEventPublisher)
    assert events.events == [("TermPublished", {"term_id": "fsm"})]


@pytest.mark.asyncio
async def test_submit_review_candidate_lands_pending(term: Term) -> None:
    uow = InMemoryUnitOfWork()
    use_case = SubmitReviewCandidate(uow)

    candidate = await use_case.execute(
        term=term,
        source_type="dependency_manifest",
        source_file="pyproject.toml",
        confidence="high",
    )

    assert candidate.id is not None
    assert candidate.status == ReviewStatus.PENDING
    assert candidate.term == term
    # Never auto-promoted, regardless of confidence.
    assert await uow.terms.by_id(term.id) is None


@pytest.mark.asyncio
async def test_list_review_candidates_filters_by_status(term: Term) -> None:
    uow = InMemoryUnitOfWork()
    await SubmitReviewCandidate(uow).execute(term, "dependency_manifest", "x", "high")

    pending = await ListReviewCandidates(uow).execute(ReviewStatus.PENDING)
    approved = await ListReviewCandidates(uow).execute(ReviewStatus.APPROVED)

    assert len(pending) == 1
    assert approved == ()


@pytest.mark.asyncio
async def test_approve_review_candidate_publishes_the_term(term: Term) -> None:
    uow = InMemoryUnitOfWork()
    candidate = await SubmitReviewCandidate(uow).execute(
        term, "dependency_manifest", "x", "high"
    )
    assert candidate.id is not None

    published = await ApproveReviewCandidate(uow).execute(candidate.id)

    assert published == term
    assert await uow.terms.by_id(term.id) == term
    approved = await uow.review_queue.by_id(candidate.id)
    assert approved is not None
    assert approved.status == ReviewStatus.APPROVED
    events = uow.events
    assert isinstance(events, InMemoryEventPublisher)
    assert events.events == [("TermPublished", {"term_id": term.id})]


@pytest.mark.asyncio
async def test_approve_review_candidate_raises_when_missing() -> None:
    with pytest.raises(ValueError, match="not found"):
        await ApproveReviewCandidate(InMemoryUnitOfWork()).execute(999)


@pytest.mark.asyncio
async def test_approve_review_candidate_raises_when_not_pending(term: Term) -> None:
    uow = InMemoryUnitOfWork()
    candidate = await SubmitReviewCandidate(uow).execute(
        term, "dependency_manifest", "x", "high"
    )
    assert candidate.id is not None
    await ApproveReviewCandidate(uow).execute(candidate.id)

    with pytest.raises(ReviewCandidateNotPending) as exc_info:
        await ApproveReviewCandidate(uow).execute(candidate.id)
    assert exc_info.value.candidate_id == candidate.id
    assert exc_info.value.status == ReviewStatus.APPROVED


@pytest.mark.asyncio
async def test_reject_review_candidate_never_publishes(term: Term) -> None:
    uow = InMemoryUnitOfWork()
    candidate = await SubmitReviewCandidate(uow).execute(
        term, "dependency_manifest", "x", "high"
    )
    assert candidate.id is not None

    await RejectReviewCandidate(uow).execute(candidate.id)

    rejected = await uow.review_queue.by_id(candidate.id)
    assert rejected is not None
    assert rejected.status == ReviewStatus.REJECTED
    assert await uow.terms.by_id(term.id) is None


@pytest.mark.asyncio
async def test_reject_review_candidate_raises_when_missing() -> None:
    with pytest.raises(ValueError, match="not found"):
        await RejectReviewCandidate(InMemoryUnitOfWork()).execute(999)
