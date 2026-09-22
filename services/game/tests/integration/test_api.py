"""API integration tests."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from game_service.api import dependencies
from game_service.api.app import app
from game_service.api.dependencies import get_term_stats_repository
from game_service.api.dependencies import get_unit_of_work
from game_service.domain.outcome import Verdict
from game_service.domain.round import GameRound
from game_service.domain.round import RoundMode
from game_service.domain.term import Category
from game_service.domain.term import Difficulty
from game_service.domain.term import Term
from game_service.infrastructure.memory import InMemoryTermStatsRepository
from game_service.infrastructure.memory import InMemoryUnitOfWork
from game_service.infrastructure.term_cache_invalidator import ConsumerHealth


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client_with_uow_term() -> Generator[TestClient]:
    """A client whose in-memory term bank has "uow" pre-seeded.

    Overrides get_unit_of_work rather than relying on the real DB fallback,
    keeping this test independent of DATABASE_URL/lifespan.
    """
    term = Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=(
            "Pattern that groups related changes into one transactional unit.",
        ),
        aliases=("Unit-of-Work",),
        categories=(Category(slug="architecture"),),
        difficulty=Difficulty.HARD,
        examples=("Committing several repository writes as one transaction.",),
    )
    uow = InMemoryUnitOfWork(terms={"uow": term})

    async def override_get_unit_of_work():
        yield uow

    app.dependency_overrides[get_unit_of_work] = override_get_unit_of_work
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.fixture
def client_and_uow() -> Generator[tuple[TestClient, InMemoryUnitOfWork]]:
    """Same override as client_with_uow_term, but also exposes the
    InMemoryUnitOfWork so a test can inject a round directly (e.g. an
    already-expired Sprint round no HTTP call could produce without
    sleeping)."""
    term = Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=(
            "Pattern that groups related changes into one transactional unit.",
        ),
        categories=(Category(slug="architecture"),),
    )
    uow = InMemoryUnitOfWork(terms={"uow": term})

    async def override_get_unit_of_work():
        yield uow

    app.dependency_overrides[get_unit_of_work] = override_get_unit_of_work
    with TestClient(app) as client:
        yield client, uow
    app.dependency_overrides.pop(get_unit_of_work, None)


def test_health(client: TestClient) -> None:
    """GET /health returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready(client: TestClient) -> None:
    """GET /ready returns ready when no Kafka consumer is configured."""
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_degrades_when_consumer_is_stale(client: TestClient) -> None:
    """A dead term cache invalidator degrades readiness, never fails it."""
    stale_health = ConsumerHealth()
    stale_health.last_alive_at -= 100.0
    dependencies._consumer_health = stale_health
    try:
        response = client.get("/ready")
    finally:
        dependencies._consumer_health = None

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["reason"] == "term_cache_invalidator_stale"


def test_ready_degrades_when_stats_consumer_is_stale(client: TestClient) -> None:
    """A dead answer-graded stats consumer degrades readiness, never fails it."""
    stale_health = ConsumerHealth()
    stale_health.last_alive_at -= 100.0
    dependencies._stats_consumer_health = stale_health
    try:
        response = client.get("/ready")
    finally:
        dependencies._stats_consumer_health = None

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["reason"] == "answer_graded_stats_consumer_stale"


def test_submit_answer_exact_match(client_with_uow_term: TestClient) -> None:
    """POST /game-rounds/{id}/answers/submit with exact match returns CORRECT."""
    response = client_with_uow_term.post(
        "/game-rounds/s1/answers/submit",
        json={
            "term_id": "uow",
            "answer": "Unit of Work",
        },
    )
    assert response.status_code == 200
    assert response.json()["verdict"] == "correct"


def test_submit_answer_offensive_answer_is_flagged(
    client_with_uow_term: TestClient,
) -> None:
    """An offensive answer is rejected before any correctness grading, via
    the real DI-wired evaluator (ProfanityGrader is baked into
    api.dependencies.get_answer_evaluator, not just build_deterministic_evaluator).
    """
    response = client_with_uow_term.post(
        "/game-rounds/s1/answers/submit",
        json={"term_id": "uow", "answer": "fuck this game"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "incorrect"
    assert body["matched_via"] == "flagged"
    assert body["score"] == 0


def test_submit_answer_stream_exact_match(client_with_uow_term: TestClient) -> None:
    """POST .../submit/stream with an exact match streams a single 'graded'
    SSE event — nothing to stream when the deterministic verdict is CORRECT.
    """
    with client_with_uow_term.stream(
        "POST",
        "/game-rounds/s1/answers/submit/stream",
        json={"term_id": "uow", "answer": "Unit of Work"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert "event: graded" in body
    assert "rationale_delta" not in body
    assert '"verdict":"correct"' in body


def test_submit_answer_stream_term_not_found(
    client_with_uow_term: TestClient,
) -> None:
    """A nonexistent term surfaces as an 'error' SSE event: the response has
    already started streaming (200) by the time grading fails, so it can't
    become an HTTP 404.
    """
    with client_with_uow_term.stream(
        "POST",
        "/game-rounds/s1/answers/submit/stream",
        json={"term_id": "nonexistent", "answer": "anything"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: error" in body


def test_submit_answer_missing_term_id(client: TestClient) -> None:
    """POST with missing term_id returns 422."""
    response = client.post(
        "/game-rounds/s1/answers/submit",
        json={
            "answer": "Unit of Work",
        },
    )
    assert response.status_code == 422


def test_submit_answer_missing_answer(client: TestClient) -> None:
    """POST with missing answer returns 422."""
    response = client.post(
        "/game-rounds/s1/answers/submit",
        json={
            "term_id": "uow",
        },
    )
    assert response.status_code == 422


def test_submit_answer_empty_term_id(client: TestClient) -> None:
    """POST with empty term_id returns 422."""
    response = client.post(
        "/game-rounds/s1/answers/submit",
        json={
            "term_id": "",
            "answer": "Unit of Work",
        },
    )
    assert response.status_code == 422


def test_submit_answer_empty_answer(client: TestClient) -> None:
    """POST with empty answer returns 422."""
    response = client.post(
        "/game-rounds/s1/answers/submit",
        json={
            "term_id": "uow",
            "answer": "",
        },
    )
    assert response.status_code == 422


def test_create_round_mints_an_id(client_with_uow_term: TestClient) -> None:
    """POST /game-rounds returns a fresh round with a server-minted id."""
    response = client_with_uow_term.post("/game-rounds")

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["answers"] == []


def test_create_round_ids_are_distinct(client_with_uow_term: TestClient) -> None:
    """Two POSTs mint two different round ids."""
    first = client_with_uow_term.post("/game-rounds").json()
    second = client_with_uow_term.post("/game-rounds").json()

    assert first["id"] != second["id"]


def test_create_round_sprint_returns_mode_and_remaining_seconds(
    client_with_uow_term: TestClient,
) -> None:
    """POST /game-rounds with mode=sprint surfaces the countdown."""
    response = client_with_uow_term.post(
        "/game-rounds", json={"mode": "sprint", "duration_seconds": 30}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "sprint"
    assert body["remaining_seconds"] == pytest.approx(30.0, abs=1.0)


def test_create_round_classic_has_no_remaining_seconds(
    client_with_uow_term: TestClient,
) -> None:
    """Classic (the default) has no countdown."""
    response = client_with_uow_term.post("/game-rounds")

    body = response.json()
    assert body["mode"] == "classic"
    assert body["remaining_seconds"] is None


def test_create_round_classic_defaults_new_mode_fields(
    client_with_uow_term: TestClient,
) -> None:
    """A freshly created Classic round is never over and has no mode-specific
    counters — is_over/lives_remaining/terms_remaining are Survival/Boss/
    Daily 20 concerns, all null or false for Classic."""
    response = client_with_uow_term.post("/game-rounds")

    body = response.json()
    assert body["is_over"] is False
    assert body["lives_remaining"] is None
    assert body["terms_remaining"] is None


def test_create_round_accepts_every_new_mode_value(
    client_with_uow_term: TestClient,
) -> None:
    """POST /game-rounds accepts survival/boss/daily_20 without validation
    error — CreateRoundRequest's mode field already accepts every RoundMode
    member automatically; this locks that in."""
    for mode in ("survival", "boss", "daily_20"):
        response = client_with_uow_term.post("/game-rounds", json={"mode": mode})
        assert response.status_code == 201, mode
        assert response.json()["mode"] == mode


def test_submit_answer_rejects_expired_sprint_round(
    client_and_uow: tuple[TestClient, InMemoryUnitOfWork],
) -> None:
    """Submitting to a Sprint round past its deadline returns 422."""
    client, uow = client_and_uow
    started = datetime.now(UTC) - timedelta(seconds=61)
    expired = GameRound.start(started, mode=RoundMode.SPRINT, duration_seconds=60)
    asyncio.run(uow.rounds.save(expired))

    response = client.post(
        f"/game-rounds/{expired.id}/answers/submit",
        json={"term_id": "uow", "answer": "Unit of Work"},
    )

    assert response.status_code == 422


def test_get_round_not_found(client_with_uow_term: TestClient) -> None:
    """GET /game-rounds/{id} for a round that never submitted returns 404."""
    response = client_with_uow_term.get("/game-rounds/never-existed")
    assert response.status_code == 404


def test_get_round_after_submit(client_with_uow_term: TestClient) -> None:
    """GET /game-rounds/{id} reflects a prior submission in the same round."""
    client_with_uow_term.post(
        "/game-rounds/s1/answers/submit",
        json={"term_id": "uow", "answer": "Unit of Work"},
    )

    response = client_with_uow_term.get("/game-rounds/s1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "s1"
    assert len(body["answers"]) == 1
    assert body["answers"][0]["term_id"] == "uow"
    assert body["answers"][0]["verdict"] == "correct"


@pytest.fixture
def client_with_term_stats() -> Generator[
    tuple[TestClient, InMemoryTermStatsRepository]
]:
    """Overrides get_term_stats_repository with a fresh in-memory repository
    a test can seed directly, and get_unit_of_work with a bank pre-seeded
    with "uow" — GET .../stats checks term existence via UnitOfWork first."""
    term = Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=(
            "Pattern that groups related changes into one transactional unit.",
        ),
        categories=(Category(slug="architecture"),),
    )
    uow = InMemoryUnitOfWork(terms={"uow": term})
    repo = InMemoryTermStatsRepository()

    async def override_get_unit_of_work():
        yield uow

    async def override_get_term_stats_repository():
        yield repo

    app.dependency_overrides[get_unit_of_work] = override_get_unit_of_work
    app.dependency_overrides[get_term_stats_repository] = (
        override_get_term_stats_repository
    )
    with TestClient(app) as client:
        yield client, repo
    app.dependency_overrides.pop(get_unit_of_work, None)
    app.dependency_overrides.pop(get_term_stats_repository, None)


def test_get_term_stats_for_a_term_with_no_data(
    client_with_term_stats: tuple[TestClient, InMemoryTermStatsRepository],
) -> None:
    """A term with no graded answers yet returns zeros, not a 404."""
    client, _ = client_with_term_stats

    response = client.get("/terms/uow/stats")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "term_id": "uow",
        "correct_count": 0,
        "partial_count": 0,
        "incorrect_count": 0,
        "observed_difficulty": None,
    }


def test_get_term_stats_reflects_recorded_verdicts(
    client_with_term_stats: tuple[TestClient, InMemoryTermStatsRepository],
) -> None:
    """Stats recorded against the shared repository (as the consumer would)
    are visible through the read endpoint."""
    client, repo = client_with_term_stats
    asyncio.run(repo.record("uow", Verdict.CORRECT))
    asyncio.run(repo.record("uow", Verdict.PARTIAL))
    asyncio.run(repo.record("uow", Verdict.INCORRECT))

    response = client.get("/terms/uow/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["correct_count"] == 1
    assert body["partial_count"] == 1
    assert body["incorrect_count"] == 1
    assert body["observed_difficulty"] == pytest.approx(2 / 3)


def test_get_term_stats_for_a_nonexistent_term(
    client_with_term_stats: tuple[TestClient, InMemoryTermStatsRepository],
) -> None:
    """A term that doesn't exist in the bank at all is a 404, distinct from
    a real term with no graded answers yet (which is a 200 of zeros)."""
    client, _ = client_with_term_stats

    response = client.get("/terms/nonexistent/stats")

    assert response.status_code == 404


@pytest.fixture
def client_with_two_categories() -> Generator[TestClient]:
    """A bank with one term in "architecture" and one in "python-keywords" —
    lets a test prove category scoping actually narrows the pick."""
    uow_term = Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("Pattern that groups related changes into one unit.",),
        categories=(Category(slug="architecture"),),
    )
    lambda_term = Term(
        id="lambda",
        term="lambda",
        expansion="anonymous function",
        definitions=("A function defined without a name.",),
        categories=(Category(slug="python-keywords"),),
    )
    uow = InMemoryUnitOfWork(terms={"uow": uow_term, "lambda": lambda_term})

    async def override_get_unit_of_work():
        yield uow

    app.dependency_overrides[get_unit_of_work] = override_get_unit_of_work
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_unit_of_work, None)


def test_get_random_term_scoped_to_category(
    client_with_two_categories: TestClient,
) -> None:
    """GET /terms/random?category=... only returns terms in that collection."""
    response = client_with_two_categories.get(
        "/terms/random", params={"category": "python-keywords"}
    )

    assert response.status_code == 200
    assert response.json()["id"] == "lambda"


def test_get_random_term_category_with_no_terms_is_404(
    client_with_two_categories: TestClient,
) -> None:
    """A category slug that matches nothing maps to the same 404 as an
    empty bank — ValueError from the use case, handled generically."""
    response = client_with_two_categories.get(
        "/terms/random", params={"category": "nonexistent-category"}
    )

    assert response.status_code == 404


def test_get_term_categories_lists_every_collection(
    client_with_two_categories: TestClient,
) -> None:
    response = client_with_two_categories.get("/terms/categories")

    assert response.status_code == 200
    assert response.json() == {"categories": ["architecture", "python-keywords"]}
