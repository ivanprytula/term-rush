"""FastAPI dependency injection."""

from __future__ import annotations

from application.use_cases import SubmitAnswer
from infrastructure.memory import InMemoryUnitOfWork


def get_submit_answer_use_case() -> SubmitAnswer:
    """Provide the SubmitAnswer use case.

    Phase 1: in-memory UoW. Phase 1d: inject from a container.
    """
    uow = InMemoryUnitOfWork()
    return SubmitAnswer(uow)
