import logging
import uuid

from fastapi import FastAPI
from fastapi import Request
from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry.baggage import set_baggage

from api.routers import answers
from infrastructure.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Term Rush — game service")


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
    """Readiness: safe to route traffic. Will check deps once they exist."""
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
