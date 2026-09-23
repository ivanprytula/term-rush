"""Read-only gameplay configuration endpoint."""

from fastapi import APIRouter
from fastapi import status

from game_service.api.schemas import GameConfigResponse
from game_service.api.schemas import GameModeConfigResponse
from game_service.api.schemas import RubricConfigResponse
from game_service.api.schemas import SprintConfigResponse
from game_service.domain import constants
from game_service.domain.round import RoundMode

router = APIRouter(prefix="/game-config", tags=["configuration"])


def build_game_config() -> GameConfigResponse:
    """Build gameplay limits and capabilities for frontend clients.

    Shared by the REST endpoint and the GraphQL sessionScreen query
    (ADR-0010) so the two surfaces can't drift on what "game config" means.
    """
    return GameConfigResponse(
        modes=[
            GameModeConfigResponse(
                mode=RoundMode.CLASSIC,
                max_answers=constants.ROUND_MAX_ANSWERS,
                timed=False,
                llm_grading="optional",
            ),
            GameModeConfigResponse(
                mode=RoundMode.SPRINT,
                timed=True,
                llm_grading="disabled",
            ),
            GameModeConfigResponse(
                mode=RoundMode.SURVIVAL,
                timed=False,
                llm_grading="optional",
            ),
            GameModeConfigResponse(
                mode=RoundMode.BOSS,
                max_answers=constants.BOSS_ROUND_SIZE,
                timed=False,
                llm_grading="forced",
            ),
            GameModeConfigResponse(
                mode=RoundMode.DAILY_20,
                max_answers=constants.DAILY_20_ROUND_SIZE,
                timed=False,
                llm_grading="disabled",
            ),
        ],
        sprint=SprintConfigResponse(
            default_duration_seconds=constants.DEFAULT_SPRINT_DURATION_SECONDS,
            min_duration_seconds=constants.MIN_SPRINT_DURATION_SECONDS,
            max_duration_seconds=constants.MAX_SPRINT_DURATION_SECONDS,
            duration_options_seconds=[10, 30, 60, 120, 300],
        ),
        survival_lives=constants.SURVIVAL_LIVES,
        daily_term_count=constants.DAILY_20_ROUND_SIZE,
        answer_max_length=constants.ANSWER_MAX_LEN,
        score_max=constants.MAX_SCORE,
        rubric=RubricConfigResponse(
            concept=constants.CONCEPT_WEIGHT,
            expansion=constants.EXPANSION_WEIGHT,
            purpose=constants.PURPOSE_WEIGHT,
            example=constants.EXAMPLE_WEIGHT,
        ),
    )


@router.get("", response_model=GameConfigResponse, status_code=status.HTTP_200_OK)
def get_game_config() -> GameConfigResponse:
    """Return gameplay limits and capabilities for frontend clients."""
    return build_game_config()
