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


_CANDIDATE_PAYLOAD = {
    "term": {
        "id": "fsm",
        "term": "FSM",
        "expansion": "Finite State Machine",
        "definitions": ["A model with states and transitions."],
        "categories": ["theory"],
    },
    "source_type": "dependency_manifest",
    "source_file": "pyproject.toml",
    "confidence": "high",
}


def test_submit_review_candidate_lands_pending(
    client_with_empty_uow: TestClient,
) -> None:
    response = client_with_empty_uow.post(
        "/review-queue/candidates", json=_CANDIDATE_PAYLOAD
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["term"]["id"] == "fsm"

    # Never auto-promoted.
    term_response = client_with_empty_uow.get("/terms/fsm")
    assert term_response.status_code == 404


def test_list_review_candidates_defaults_to_pending(
    client_with_empty_uow: TestClient,
) -> None:
    client_with_empty_uow.post("/review-queue/candidates", json=_CANDIDATE_PAYLOAD)

    response = client_with_empty_uow.get("/review-queue")

    assert response.status_code == 200
    assert len(response.json()["candidates"]) == 1


def test_approve_review_candidate_publishes_the_term(
    client_with_empty_uow: TestClient,
) -> None:
    submitted = client_with_empty_uow.post(
        "/review-queue/candidates", json=_CANDIDATE_PAYLOAD
    ).json()

    response = client_with_empty_uow.post(f"/review-queue/{submitted['id']}/approve")

    assert response.status_code == 200
    assert response.json()["id"] == "fsm"

    term_response = client_with_empty_uow.get("/terms/fsm")
    assert term_response.status_code == 200


def test_approve_review_candidate_missing_returns_404(
    client_with_empty_uow: TestClient,
) -> None:
    response = client_with_empty_uow.post("/review-queue/999/approve")

    assert response.status_code == 404


def test_approve_review_candidate_already_approved_returns_409(
    client_with_empty_uow: TestClient,
) -> None:
    submitted = client_with_empty_uow.post(
        "/review-queue/candidates", json=_CANDIDATE_PAYLOAD
    ).json()
    client_with_empty_uow.post(f"/review-queue/{submitted['id']}/approve")

    response = client_with_empty_uow.post(f"/review-queue/{submitted['id']}/approve")

    assert response.status_code == 409
    body = response.json()
    assert body["candidate_id"] == submitted["id"]
    assert body["current_status"] == "approved"
    assert body["required_status"] == "pending"


def test_reject_review_candidate_never_publishes(
    client_with_empty_uow: TestClient,
) -> None:
    submitted = client_with_empty_uow.post(
        "/review-queue/candidates", json=_CANDIDATE_PAYLOAD
    ).json()

    response = client_with_empty_uow.post(f"/review-queue/{submitted['id']}/reject")

    assert response.status_code == 204
    term_response = client_with_empty_uow.get("/terms/fsm")
    assert term_response.status_code == 404


_CHUNKS_PAYLOAD = {
    "chunks": [
        {
            "text": "first chunk of the contract",
            "source_file": "contract.pdf",
            "chunk_index": 0,
            "char_start": 0,
            "char_end": 28,
        },
        {
            "text": "second chunk of the contract",
            "source_file": "contract.pdf",
            "chunk_index": 1,
            "char_start": 20,
            "char_end": 49,
        },
    ]
}


def test_ingest_document_chunks_persists_and_returns_ids(
    client_with_empty_uow: TestClient,
) -> None:
    response = client_with_empty_uow.post("/document-chunks", json=_CHUNKS_PAYLOAD)

    assert response.status_code == 201
    chunks = response.json()["chunks"]
    assert len(chunks) == 2
    assert all(c["id"] is not None for c in chunks)


def test_list_document_chunks_by_source_returns_only_matching(
    client_with_empty_uow: TestClient,
) -> None:
    client_with_empty_uow.post("/document-chunks", json=_CHUNKS_PAYLOAD)
    client_with_empty_uow.post(
        "/document-chunks",
        json={
            "chunks": [
                {
                    "text": "unrelated chunk",
                    "source_file": "other.pdf",
                    "chunk_index": 0,
                    "char_start": 0,
                    "char_end": 16,
                }
            ]
        },
    )

    response = client_with_empty_uow.get(
        "/document-chunks", params={"source_file": "contract.pdf"}
    )

    assert response.status_code == 200
    chunks = response.json()["chunks"]
    assert len(chunks) == 2
    assert all(c["source_file"] == "contract.pdf" for c in chunks)


def test_list_document_chunks_by_source_empty_when_no_match(
    client_with_empty_uow: TestClient,
) -> None:
    response = client_with_empty_uow.get(
        "/document-chunks", params={"source_file": "missing.pdf"}
    )

    assert response.status_code == 200
    assert response.json()["chunks"] == []
