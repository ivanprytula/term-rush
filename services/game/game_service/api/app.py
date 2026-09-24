import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry.baggage import set_baggage

from game_service.api import dependencies
from game_service.api.dependencies import _init_session_factory
from game_service.api.graphql.schema import graphql_router
from game_service.api.routers import answers
from game_service.api.routers import config
from game_service.api.routers import game_rounds
from game_service.api.routers import leaderboard
from game_service.api.routers import terms
from game_service.domain.round import RoundExpired
from game_service.domain.round import RoundFull
from game_service.domain.round import RoundOver
from game_service.infrastructure.answer_graded_stats import (
    _supervise as _supervise_stats,
)
from game_service.infrastructure.logging import configure_logging
from game_service.infrastructure.term_cache_invalidator import (
    _supervise as _supervise_term_cache,
)

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize database, gRPC channel, and Kafka producer/consumer on
    startup; run both consumer supervisors for the app's life; clean up
    everything on shutdown.

    The two supervisors run inside one TaskGroup wrapping the yield, instead
    of each being a separately tracked asyncio.Task cancelled by hand: exiting
    the `async with` (app shutdown) cancels and awaits both together. Each
    _supervise loop already swallows its own unexpected exceptions and
    restarts (see term_cache_invalidator._supervise), so in practice a
    TaskGroup failure here would only ever be a CancelledError on shutdown —
    the same case the old manual stop_consumer_task calls handled, just
    without a second place to track task ownership.
    """
    try:
        await _init_session_factory()
        logger.info("Database initialized")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        raise
    try:
        async with asyncio.TaskGroup() as tg:
            supervisor_tasks: list[asyncio.Task[None]] = []
            if dependencies._kafka_consumer is not None:
                assert dependencies._term_repository is not None
                assert dependencies._consumer_health is not None
                supervisor_tasks.append(
                    tg.create_task(
                        _supervise_term_cache(
                            dependencies._kafka_consumer,
                            dependencies._term_repository,
                            dependencies._consumer_health,
                        )
                    )
                )
            if dependencies._stats_consumer is not None:
                assert dependencies._stats_consumer_health is not None
                supervisor_tasks.append(
                    tg.create_task(
                        _supervise_stats(
                            dependencies._stats_consumer,
                            dependencies._session_factory,
                            dependencies._stats_consumer_health,
                        )
                    )
                )
            yield
            # Reaching here means the app is shutting down: cancel both
            # supervisors (each loops until cancelled — it never finishes on
            # its own) so the TaskGroup's __aexit__ can join them instead of
            # waiting on them forever.
            for task in supervisor_tasks:
                task.cancel()
    finally:
        if dependencies._kafka_consumer is not None:
            await dependencies._kafka_consumer.stop()
            logger.info("Kafka consumer stopped")
        if dependencies._stats_consumer is not None:
            await dependencies._stats_consumer.stop()
            logger.info("Answer-graded stats consumer stopped")
        if dependencies._grpc_channel is not None:
            await dependencies._grpc_channel.close()
            logger.info("gRPC channel closed")
        if dependencies._kafka_producer is not None:
            await dependencies._kafka_producer.stop()
            logger.info("Kafka producer stopped")
        if dependencies._engine is not None:
            await dependencies._engine.dispose()
            logger.info("Database engine disposed")


app = FastAPI(title="Term Rush — game service", lifespan=lifespan)


@app.middleware("http")
async def inject_task_name(request: Request, call_next):
    """Inject taskName baggage from request header or generate one."""
    task_name = request.headers.get("x-task-name", f"Task-{uuid.uuid4().hex[:8]}")
    set_baggage("taskName", task_name)
    return await call_next(request)


app.include_router(answers.router)
app.include_router(config.router)
app.include_router(game_rounds.router)
app.include_router(leaderboard.router)
app.include_router(terms.router)
app.include_router(graphql_router, prefix="/graphql")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up. Never checks dependencies."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Readiness: safe to route traffic.

    Never hard-fails on either Kafka consumer: a stale/dead term-cache
    invalidator means cache invalidation has degraded to the 300s TTL
    fallback; a stale/dead stats consumer means term difficulty stats stop
    updating. Neither means the service can't serve requests. Surfaced as
    a status string so it's visible without gating traffic. Checked in
    this order so the pre-existing term_cache_invalidator_stale contract
    (see test_ready_degrades_when_consumer_is_stale) is unaffected by
    adding a second consumer.
    """
    health = dependencies.get_consumer_health()
    if health is not None and health.is_stale():
        return {"status": "degraded", "reason": "term_cache_invalidator_stale"}
    stats_health = dependencies.get_stats_consumer_health()
    if stats_health is not None and stats_health.is_stale():
        return {"status": "degraded", "reason": "answer_graded_stats_consumer_stale"}
    return {"status": "ready"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, _exc: RequestValidationError
) -> JSONResponse:
    """Client-friendly validation error response."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"error": "Invalid request", "status_code": 422},
    )


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    """Domain errors mapped to 404."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": str(exc), "status_code": 404},
    )


@app.exception_handler(RoundFull)
async def round_full_handler(_request: Request, _exc: RoundFull) -> JSONResponse:
    """A round that has reached its answer limit is a client-side error."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"error": "Round has reached its answer limit", "status_code": 422},
    )


@app.exception_handler(RoundExpired)
async def round_expired_handler(_request: Request, _exc: RoundExpired) -> JSONResponse:
    """A Sprint round's timer has run out — reject further answers."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"error": "Round has expired", "status_code": 422},
    )


@app.exception_handler(RoundOver)
async def round_over_handler(_request: Request, _exc: RoundOver) -> JSONResponse:
    """A round has reached its mode's terminal state (Survival's lives
    exhausted, a Boss round's single answer already submitted, Daily 20's
    term cap reached) — reject further answers."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"error": "Round is over", "status_code": 422},
    )
