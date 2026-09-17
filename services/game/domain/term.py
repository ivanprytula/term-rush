"""The term knowledge object.

This is the central domain entity. It is deliberately decoupled from any game
mode: the same object powers Sprint, Survival, Boss Round, flashcards, search
and spaced repetition. A term is knowledge, not a game card.
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator


class Difficulty(IntEnum):
    """How hard a term is to explain, not to recognize.

    Drives spawn rates, rubric strictness and Boss Round eligibility.
    """

    TRIVIAL = 1
    EASY = 2
    MODERATE = 3
    HARD = 4
    EXPERT = 5


class Category(BaseModel):
    """A tag namespace. Kept as a value object rather than a bare string so
    category-specific rules (e.g. AI terms decay faster) have somewhere to live.
    """

    model_config = {"frozen": True}

    slug: str = Field(pattern=r"^[a-z][a-z0-9-]*$", max_length=32)

    def __str__(self) -> str:
        return self.slug


class Term(BaseModel):
    """A unit of knowledge.

    Frozen: terms are replaced by content-service publishing a new version, never
    mutated in place by the game.
    """

    model_config = {"frozen": True}

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    term: str = Field(min_length=1, max_length=64)
    expansion: str = Field(min_length=1, max_length=256)

    definitions: tuple[str, ...] = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    categories: tuple[Category, ...] = Field(min_length=1)
    difficulty: Difficulty = Difficulty.MODERATE

    examples: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    common_mistakes: tuple[str, ...] = ()

    @field_validator("aliases", "definitions", "examples")
    @classmethod
    def _reject_blank_entries(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not entry.strip() for entry in v):
            raise ValueError("entries must not be blank")
        return v

    @property
    def primary_definition(self) -> str:
        return self.definitions[0]

    @property
    def is_boss_eligible(self) -> bool:
        """Boss Rounds demand a real explanation, so they need a term that has
        enough substance to grade against a four-part rubric.
        """
        return (
            self.difficulty >= Difficulty.MODERATE
            and bool(self.examples)
            and len(self.primary_definition) >= 40
        )

    def all_acceptable_expansions(self) -> tuple[str, ...]:
        """The expansion plus every alias. What an exact/alias grader matches on."""
        return (self.expansion, *self.aliases)
