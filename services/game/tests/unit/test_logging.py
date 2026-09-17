"""Verify structured logging redacts sensitive fields."""

import json
import logging
from io import StringIO

import pytest

from infrastructure.logging import StructuredFormatter


@pytest.fixture
def log_stream():
    """Capture log output."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredFormatter())
    logger = logging.getLogger("test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield stream
    logger.removeHandler(handler)


def test_redacts_answer_field(log_stream):
    """Sensitive fields like 'answer' must be redacted."""
    logger = logging.getLogger("test")
    logger.info("Processing", extra={"answer": "secret_answer_123"})

    output = log_stream.getvalue()
    log_obj = json.loads(output.strip())

    assert log_obj["extra"]["answer"] == "[REDACTED]"
    assert "secret_answer_123" not in output


def test_redacts_nested_fields(log_stream):
    """Redaction works recursively in nested dicts."""
    logger = logging.getLogger("test")
    logger.info("Processing", extra={"data": {"password": "pass123", "name": "user"}})

    output = log_stream.getvalue()
    log_obj = json.loads(output.strip())

    assert log_obj["extra"]["data"]["password"] == "[REDACTED]"
    assert log_obj["extra"]["data"]["name"] == "user"
    assert "pass123" not in output


def test_preserves_non_sensitive_fields(log_stream):
    """Non-sensitive fields pass through unmodified."""
    logger = logging.getLogger("test")
    logger.info("Processing", extra={"user_id": 42, "session": "abc"})

    output = log_stream.getvalue()
    log_obj = json.loads(output.strip())

    assert log_obj["extra"]["user_id"] == 42
    assert log_obj["extra"]["session"] == "abc"


def test_log_structure(log_stream):
    """Logs have required OTel-compatible fields."""
    logger = logging.getLogger("test")
    logger.info("test message")

    output = log_stream.getvalue()
    log_obj = json.loads(output.strip())

    assert "timestamp" in log_obj
    assert "level" in log_obj
    assert "logger" in log_obj
    assert "message" in log_obj
    assert log_obj["level"] == "INFO"
    assert log_obj["message"] == "test message"
