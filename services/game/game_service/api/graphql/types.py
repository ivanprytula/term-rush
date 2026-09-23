"""GraphQL types mirroring the REST schemas they aggregate.

Field names/shapes intentionally track api.schemas (ADR-0010: two schemas
describing overlapping data, kept in sync by hand). Conversion methods
mirror that module's from_* staticmethod convention.
"""

from __future__ import annotations

from enum import Enum

import strawberry

from game_service.api.schemas import GameConfigResponse
from game_service.api.schemas import GameModeConfigResponse
from game_service.api.schemas import RubricConfigResponse
from game_service.api.schemas import SprintConfigResponse
from game_service.domain.round import RoundMode as DomainRoundMode
from game_service.domain.term import Term


@strawberry.enum
class RoundMode(Enum):
    """GraphQL-owned mirror of domain.round.RoundMode.

    GraphQL enums serialize by Python member NAME, not .value — Strawberry
    has no separate wire-value concept the way StrEnum.value does for
    Pydantic. A plain Strawberry enum built from the domain StrEnum
    directly would therefore serialize as CLASSIC, DAILY_20, ..., silently
    diverging from the REST GameModeConfigResponse.mode wire value
    ("classic", "daily_20", ...). This mirror's member names are lowercase
    to match REST, at the cost of one more place to update if a mode is
    renamed.
    """

    classic = "classic"
    sprint = "sprint"
    survival = "survival"
    boss = "boss"
    daily_20 = "daily_20"

    @staticmethod
    def from_domain(mode: DomainRoundMode) -> RoundMode:
        return RoundMode(mode.value)


@strawberry.type
class GameModeConfig:
    mode: RoundMode
    max_answers: int | None
    timed: bool
    llm_grading: str

    @staticmethod
    def from_response(response: GameModeConfigResponse) -> GameModeConfig:
        return GameModeConfig(
            mode=RoundMode.from_domain(response.mode),
            max_answers=response.max_answers,
            timed=response.timed,
            llm_grading=response.llm_grading,
        )


@strawberry.type
class SprintConfig:
    default_duration_seconds: int
    min_duration_seconds: int
    max_duration_seconds: int
    duration_options_seconds: list[int]

    @staticmethod
    def from_response(response: SprintConfigResponse) -> SprintConfig:
        return SprintConfig(
            default_duration_seconds=response.default_duration_seconds,
            min_duration_seconds=response.min_duration_seconds,
            max_duration_seconds=response.max_duration_seconds,
            duration_options_seconds=response.duration_options_seconds,
        )


@strawberry.type
class RubricConfig:
    concept: int
    expansion: int
    purpose: int
    example: int

    @staticmethod
    def from_response(response: RubricConfigResponse) -> RubricConfig:
        return RubricConfig(
            concept=response.concept,
            expansion=response.expansion,
            purpose=response.purpose,
            example=response.example,
        )


@strawberry.type
class GameConfig:
    modes: list[GameModeConfig]
    sprint: SprintConfig
    survival_lives: int
    daily_term_count: int
    answer_max_length: int
    score_max: int
    rubric: RubricConfig

    @staticmethod
    def from_response(response: GameConfigResponse) -> GameConfig:
        return GameConfig(
            modes=[GameModeConfig.from_response(m) for m in response.modes],
            sprint=SprintConfig.from_response(response.sprint),
            survival_lives=response.survival_lives,
            daily_term_count=response.daily_term_count,
            answer_max_length=response.answer_max_length,
            score_max=response.score_max,
            rubric=RubricConfig.from_response(response.rubric),
        )


@strawberry.type
class TermPrompt:
    """A term presented to the player. Excludes the expansion/definitions
    so the answer isn't leaked in the prompt — same contract as
    TermPromptResponse."""

    id: str
    term: str

    @staticmethod
    def from_term(term: Term) -> TermPrompt:
        return TermPrompt(id=term.id, term=term.term)


@strawberry.type
class SessionScreen:
    game_config: GameConfig
    term_categories: list[str]
    random_term: TermPrompt | None
