"""API integration tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from content_service.api.app import app
from content_service.api.dependencies import get_unit_of_work
from content_service.domain.term import Category
from content_service.domain.term import Term
from content_service.infrastructure.memory import InMemoryUnitOfWork


def _override_with(uow: InMemoryUnitOfWork) -> Generator[TestClient]:
    """A client whose Unit of Work is pinned to the given in-memory instance.

    Overrides get_unit_of_work rather than relying on the real DB fallback,
    keeping tests independent of DATABASE_URL/lifespan.
    """

    async def override_get_unit_of_work():
        yield uow

    app.dependency_overrides[get_unit_of_work] = override_get_unit_of_work
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client_with_empty_uow() -> Generator[TestClient]:
    """A client whose in-memory term bank is empty."""
    yield from _override_with(InMemoryUnitOfWork())


@pytest.fixture
def client_with_uow_term() -> Generator[TestClient]:
    """A client whose in-memory term bank has "uow" pre-seeded."""
    term = Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("Pattern that groups related changes into one unit.",),
        categories=(Category(slug="architecture"),),
    )
    yield from _override_with(InMemoryUnitOfWork(terms={"uow": term}))


@pytest.fixture
def client_with_two_categories() -> Generator[TestClient]:
    """A bank with one term in "architecture" and one in "python-keywords"."""
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
    yield from _override_with(
        InMemoryUnitOfWork(terms={"uow": uow_term, "lambda": lambda_term})
    )


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


def test_get_random_term_returns_the_seeded_term(
    client_with_uow_term: TestClient,
) -> None:
    response = client_with_uow_term.get("/terms/random")

    assert response.status_code == 200
    assert response.json()["id"] == "uow"
    assert response.json()["expansion"] == "Unit of Work"


def test_get_random_term_404_when_bank_is_empty(
    client_with_empty_uow: TestClient,
) -> None:
    response = client_with_empty_uow.get("/terms/random")

    assert response.status_code == 404


def test_get_term_by_id_returns_the_term(client_with_uow_term: TestClient) -> None:
    response = client_with_uow_term.get("/terms/uow")

    assert response.status_code == 200
    assert response.json()["id"] == "uow"


def test_get_term_by_id_404_when_missing(client_with_uow_term: TestClient) -> None:
    response = client_with_uow_term.get("/terms/nonexistent")

    assert response.status_code == 404


def test_get_random_term_scoped_to_category(
    client_with_two_categories: TestClient,
) -> None:
    response = client_with_two_categories.get(
        "/terms/random", params={"category": "python-keywords"}
    )

    assert response.status_code == 200
    assert response.json()["id"] == "lambda"


def test_get_random_term_category_with_no_terms_is_404(
    client_with_two_categories: TestClient,
) -> None:
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


def test_publish_term_creates_a_new_term(client_with_empty_uow: TestClient) -> None:
    response = client_with_empty_uow.post(
        "/terms",
        json={
            "id": "fsm",
            "term": "FSM",
            "expansion": "Finite State Machine",
            "definitions": ["A model with states and transitions."],
            "categories": ["theory"],
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == "fsm"


def test_publish_term_missing_definitions_returns_422(
    client_with_empty_uow: TestClient,
) -> None:
    response = client_with_empty_uow.post(
        "/terms",
        json={
            "id": "fsm",
            "term": "FSM",
            "expansion": "Finite State Machine",
            "definitions": [],
            "categories": ["theory"],
        },
    )

    assert response.status_code == 422
