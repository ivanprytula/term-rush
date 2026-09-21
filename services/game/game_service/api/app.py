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
from game_service.api.routers import answers
from game_service.api.routers import game_rounds
from game_service.api.routers import leaderboard
from game_service.api.routers import terms
from game_service.domain.round import RoundExpired
from game_service.domain.round import RoundFull
from game_service.infrastructure.logging import configure_logging
from game_service.infrastructure.term_cache_invalidator import stop_consumer_task

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize database, gRPC channel, and Kafka producer/consumer on
    startup, clean up on shutdown."""
    try:
        await _init_session_factory()
        logger.info("Database initialized")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        raise
    try:
        yield
    finally:
        if dependencies._consumer_task is not None:
            await stop_consumer_task(dependencies._consumer_task)
            logger.info("Kafka consumer task stopped")
        if dependencies._kafka_consumer is not None:
            await dependencies._kafka_consumer.stop()
            logger.info("Kafka consumer stopped")
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
app.include_router(game_rounds.router)
app.include_router(leaderboard.router)
app.include_router(terms.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up. Never checks dependencies."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Readiness: safe to route traffic.

    Never hard-fails on the Kafka consumer: a stale/dead consumer means
    term cache invalidation has degraded to the 300s TTL fallback, not
    that the service can't serve requests. Surfaced as a status string
    so it's visible without gating traffic.
    """
    health = dependencies.get_consumer_health()
    if health is not None and health.is_stale():
        return {"status": "degraded", "reason": "term_cache_invalidator_stale"}
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
