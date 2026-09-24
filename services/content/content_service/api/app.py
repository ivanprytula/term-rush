import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from content_service.api import dependencies
from content_service.api.config import settings
from content_service.api.dependencies import _init_session_factory
from content_service.api.dependencies import get_unit_of_work
from content_service.api.grpc.server import serve as serve_grpc
from content_service.api.routers import document_chunks
from content_service.api.routers import review_queue
from content_service.api.routers import terms
from content_service.api.schemas import ReviewCandidateConflictResponse
from content_service.domain.review import ReviewCandidateNotPending
from content_service.infrastructure.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize database, start the gRPC server, and start the Kafka producer
    on startup, clean up on shutdown.

    The gRPC server runs in-process alongside uvicorn's event loop, on its
    own port — game-service's high-frequency term lookup goes over gRPC
    (ADR-0009); REST stays content-service's own public-ish surface.
    """
    try:
        await _init_session_factory()
        logger.info("Database initialized")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        raise
    grpc_server = await serve_grpc(get_unit_of_work, port=settings.GRPC_PORT)
    try:
        yield
    finally:
        await grpc_server.stop(grace=None)
        if dependencies._kafka_producer is not None:
            await dependencies._kafka_producer.stop()
            logger.info("Kafka producer stopped")
        if dependencies._engine is not None:
            await dependencies._engine.dispose()
            logger.info("Database engine disposed")


app = FastAPI(title="Term Rush — content service", lifespan=lifespan)

app.include_router(terms.router)
app.include_router(review_queue.router)
app.include_router(document_chunks.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up. Never checks dependencies."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Readiness: safe to route traffic."""
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


@app.exception_handler(ReviewCandidateNotPending)
async def review_candidate_not_pending_handler(
    _request: Request, exc: ReviewCandidateNotPending
) -> JSONResponse:
    """Approving/rejecting an already-decided candidate is a conflict with
    the queue's current state, not a missing resource — the body carries
    that state as typed fields so the client can branch on it directly."""
    body = ReviewCandidateConflictResponse(
        error=str(exc),
        candidate_id=exc.candidate_id,
        current_status=exc.status,
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=body.model_dump(mode="json"),
    )
