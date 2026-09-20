"""Request and response schemas for the API.

Validation happens here; the use cases work with validated domain objects.
All bounds sourced from domain.constants for consistency.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field

from content_service.domain import constants
from content_service.domain.term import Category
from content_service.domain.term import Difficulty
from content_service.domain.term import Term


class TermResponse(BaseModel):
    """A term, in full — content-service's own surface, unlike game-service's
    answer-hiding prompt response.
    """

    id: str
    term: str
    expansion: str
    definitions: tuple[str, ...]
    aliases: tuple[str, ...]
    categories: tuple[str, ...]
    difficulty: int
    examples: tuple[str, ...]
    related: tuple[str, ...]
    prerequisites: tuple[str, ...]
    common_mistakes: tuple[str, ...]

    @staticmethod
    def from_term(term: Term) -> TermResponse:
        """Convert a Term to a response."""
        return TermResponse(
            id=term.id,
            term=term.term,
            expansion=term.expansion,
            definitions=term.definitions,
            aliases=term.aliases,
            categories=tuple(str(c) for c in term.categories),
            difficulty=int(term.difficulty),
            examples=term.examples,
            related=term.related,
            prerequisites=term.prerequisites,
            common_mistakes=term.common_mistakes,
        )


class PublishTermRequest(BaseModel):
    """Authoring payload to create or replace a term."""

    id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=constants.TERM_ID_MAX_LEN
    )
    term: str = Field(
        min_length=constants.TERM_ID_MIN_LEN, max_length=constants.TERM_ID_MAX_LEN
    )
    expansion: str = Field(
        min_length=constants.TERM_ID_MIN_LEN,
        max_length=constants.TERM_DEFINITION_MAX_LEN,
    )
    definitions: tuple[str, ...] = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    categories: tuple[str, ...] = Field(min_length=1)
    difficulty: int = int(Difficulty.MODERATE)
    examples: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    common_mistakes: tuple[str, ...] = ()

    def to_term(self) -> Term:
        """Convert the validated request into a domain Term."""
        return Term(
            id=self.id,
            term=self.term,
            expansion=self.expansion,
            definitions=self.definitions,
            aliases=self.aliases,
            categories=tuple(Category(slug=c) for c in self.categories),
            difficulty=Difficulty(self.difficulty),
            examples=self.examples,
            related=self.related,
            prerequisites=self.prerequisites,
            common_mistakes=self.common_mistakes,
        )


class ErrorResponse(BaseModel):
    """Error response body.

    error: human-readable message (generic, no info leaks).
    status_code: HTTP status code (404 for term not found, 422 for
    validation, 500 for server errors).
    """

    error: str
    status_code: int = Field(ge=400, le=599, description="HTTP status code (400-599)")
