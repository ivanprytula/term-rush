import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry.baggage import set_baggage

from api.dependencies import _engine
from api.dependencies import _init_session_factory
from api.routers import answers
from infrastructure.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize database on startup, clean up on shutdown."""
    try:
        await _init_session_factory()
        logger.info("Database initialized")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        raise
    try:
        yield
    finally:
        if _engine is not None:
            await _engine.dispose()
            logger.info("Database engine disposed")


app = FastAPI(title="Term Rush — game service", lifespan=lifespan)


@app.middleware("http")
async def inject_task_name(request: Request, call_next):
    """Inject taskName baggage from request header or generate one."""
    task_name = request.headers.get("x-task-name", f"Task-{uuid.uuid4().hex[:8]}")
    set_baggage("taskName", task_name)
    return await call_next(request)


app.include_router(answers.router)


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
