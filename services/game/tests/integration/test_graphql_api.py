"""GraphQL sessionScreen query integration tests (ADR-0010)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from game_service.api.app import app
from game_service.api.dependencies import get_unit_of_work
from game_service.domain.term import Category
from game_service.domain.term import Term
from game_service.infrastructure.memory import InMemoryUnitOfWork

SESSION_SCREEN_QUERY = """
query SessionScreen($category: String) {
  sessionScreen(category: $category) {
    gameConfig {
      survivalLives
      dailyTermCount
      answerMaxLength
      scoreMax
      modes { mode maxAnswers timed llmGrading }
      sprint { defaultDurationSeconds minDurationSeconds maxDurationSeconds }
      rubric { concept expansion purpose example }
    }
    termCategories
    randomTerm { id term }
  }
}
"""


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client_with_two_categories() -> Generator[TestClient]:
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


@pytest.fixture
def client_with_empty_bank() -> Generator[TestClient]:
    uow = InMemoryUnitOfWork(terms={})

    async def override_get_unit_of_work():
        yield uow

    app.dependency_overrides[get_unit_of_work] = override_get_unit_of_work
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_unit_of_work, None)


def test_session_screen_aggregates_all_three_reads(
    client_with_two_categories: TestClient,
) -> None:
    """One query returns gameConfig, termCategories, and randomTerm — the
    three reads the session screen previously fired independently."""
    response = client_with_two_categories.post(
        "/graphql", json={"query": SESSION_SCREEN_QUERY}
    )

    assert response.status_code == 200
    body = response.json()
    assert body.get("errors") is None
    data = body["data"]["sessionScreen"]

    assert data["termCategories"] == ["architecture", "python-keywords"]
    assert data["randomTerm"]["id"] in {"uow", "lambda"}
    assert data["gameConfig"]["survivalLives"] > 0
    # GraphQL's RoundMode mirror pins its values to match REST's
    # StrEnum.value casing (see api/graphql/types.py) rather than GraphQL's
    # default member-name convention.
    mode_names = {m["mode"] for m in data["gameConfig"]["modes"]}
    assert mode_names == {"classic", "sprint", "survival", "boss", "daily_20"}


def test_session_screen_scopes_random_term_to_category(
    client_with_two_categories: TestClient,
) -> None:
    """The category argument narrows randomTerm the same way
    GET /terms/random?category= does."""
    response = client_with_two_categories.post(
        "/graphql",
        json={
            "query": SESSION_SCREEN_QUERY,
            "variables": {"category": "python-keywords"},
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]["sessionScreen"]
    assert data["randomTerm"]["id"] == "lambda"


def test_session_screen_random_term_null_on_empty_bank(
    client_with_empty_bank: TestClient,
) -> None:
    """An empty bank is a displayable state (null randomTerm), not a
    query-level GraphQL error — gameConfig and termCategories still
    resolve."""
    response = client_with_empty_bank.post(
        "/graphql", json={"query": SESSION_SCREEN_QUERY}
    )

    assert response.status_code == 200
    body = response.json()
    assert body.get("errors") is None
    data = body["data"]["sessionScreen"]
    assert data["randomTerm"] is None
    assert data["termCategories"] == []
    assert data["gameConfig"]["scoreMax"] > 0
