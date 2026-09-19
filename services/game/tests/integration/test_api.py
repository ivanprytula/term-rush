"""API integration tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.dependencies import get_unit_of_work
from domain.term import Category
from domain.term import Difficulty
from domain.term import Term
from infrastructure.memory import InMemoryUnitOfWork


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


def test_health(client: TestClient) -> None:
    """GET /health returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready(client: TestClient) -> None:
    """GET /ready returns ready."""
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_submit_answer_exact_match(client_with_uow_term: TestClient) -> None:
    """POST /sessions/{id}/answers/submit with exact match returns CORRECT."""
    response = client_with_uow_term.post(
        "/sessions/s1/answers/submit",
        json={
            "term_id": "uow",
            "answer": "Unit of Work",
        },
    )
    assert response.status_code == 200
    assert response.json()["verdict"] == "correct"


def test_submit_answer_missing_term_id(client: TestClient) -> None:
    """POST with missing term_id returns 422."""
    response = client.post(
        "/sessions/s1/answers/submit",
        json={
            "answer": "Unit of Work",
        },
    )
    assert response.status_code == 422


def test_submit_answer_missing_answer(client: TestClient) -> None:
    """POST with missing answer returns 422."""
    response = client.post(
        "/sessions/s1/answers/submit",
        json={
            "term_id": "uow",
        },
    )
    assert response.status_code == 422


def test_submit_answer_empty_term_id(client: TestClient) -> None:
    """POST with empty term_id returns 422."""
    response = client.post(
        "/sessions/s1/answers/submit",
        json={
            "term_id": "",
            "answer": "Unit of Work",
        },
    )
    assert response.status_code == 422


def test_submit_answer_empty_answer(client: TestClient) -> None:
    """POST with empty answer returns 422."""
    response = client.post(
        "/sessions/s1/answers/submit",
        json={
            "term_id": "uow",
            "answer": "",
        },
    )
    assert response.status_code == 422


def test_get_session_not_found(client_with_uow_term: TestClient) -> None:
    """GET /sessions/{id} for a session that never submitted returns 404."""
    response = client_with_uow_term.get("/sessions/never-existed")
    assert response.status_code == 404


def test_get_session_after_submit(client_with_uow_term: TestClient) -> None:
    """GET /sessions/{id} reflects a prior submission in the same session."""
    client_with_uow_term.post(
        "/sessions/s1/answers/submit",
        json={"term_id": "uow", "answer": "Unit of Work"},
    )

    response = client_with_uow_term.get("/sessions/s1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "s1"
    assert len(body["answers"]) == 1
    assert body["answers"][0]["term_id"] == "uow"
    assert body["answers"][0]["verdict"] == "correct"
