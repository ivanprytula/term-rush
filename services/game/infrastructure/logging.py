"""Structured logging with OpenTelemetry instrumentation."""

import json
import logging
import sys
from datetime import UTC
from datetime import datetime
from typing import Any


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logs compatible with OTel and log aggregators."""

    REDACTED_FIELDS = {
        "answer",
        "password",
        "token",
        "secret",
        "api_key",
        "response_body",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to JSON with redaction."""
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "trace_id"):
            log_obj["trace_id"] = record.trace_id
        if hasattr(record, "span_id"):
            log_obj["span_id"] = record.span_id

        extra = {
            k: v for k, v in record.__dict__.items() if k not in self._RESERVED_ATTRS
        }
        if extra:
            log_obj["extra"] = self._redact(extra)

        return json.dumps(log_obj)

    def _redact(self, obj: Any) -> Any:
        """Recursively redact sensitive fields."""
        if isinstance(obj, dict):
            return {
                k: self._redact(v) if k not in self.REDACTED_FIELDS else "[REDACTED]"
                for k, v in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            return [self._redact(item) for item in obj]
        return obj

    _RESERVED_ATTRS = {
        "name",
        "msg",
        "args",
        "created",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "thread",
        "threadName",
        "exc_info",
        "exc_text",
        "stack_info",
        "trace_id",
        "span_id",
    }


def configure_logging(level: str = "INFO") -> None:
    """Configure structured logging for the application."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(handler)

    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.error").handlers.clear()
