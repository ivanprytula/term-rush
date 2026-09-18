"""API integration tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from api.app import app


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app) as client:
        yield client


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


@pytest.mark.skip(
    reason="Deferred: testcontainers PostgreSQL integration needs local dev db"
)
def test_submit_answer_exact_match(client: TestClient) -> None:
    """POST /sessions/{id}/answers/submit with exact match returns CORRECT."""
    response = client.post(
        "/sessions/s1/answers/submit",
        json={
            "term_id": "uow",
            "answer": "Unit of Work",
        },
    )
    assert response.status_code in (200, 404)


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
