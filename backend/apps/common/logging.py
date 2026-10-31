"""Structured logging primitives.

A request-scoped correlation ID lives in a context variable, so every log record
emitted while handling a request carries the same identifier without threading a
parameter through each function that logs.

Log records deliberately contain no request bodies, headers, query strings, or
credentials; callers must not put such data into messages.

Two correlation IDs exist: ``request_id`` for HTTP work and ``task_id`` for Celery work. A
task publishes an event that a request then serves, or the reverse, so both appear on every
line and either can be used to find the other.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime

REQUEST_ID_ABSENT = "-"
TASK_ID_ABSENT = "-"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_task_id: ContextVar[str | None] = ContextVar("task_id", default=None)


def get_request_id() -> str | None:
    """Return the correlation ID for the current request context, if any."""
    return _request_id.get()


def set_request_id(value: str) -> Token[str | None]:
    """Bind a correlation ID to the current context and return the reset token."""
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the previous context value, typically in a ``finally`` block."""
    _request_id.reset(token)


def get_task_id() -> str | None:
    """Return the Celery task ID for the current execution, if any."""
    return _task_id.get()


def set_task_id(value: str) -> Token[str | None]:
    """Bind a task ID to the current context and return the reset token."""
    return _task_id.set(value)


def reset_task_id(token: Token[str | None]) -> None:
    """Restore the previous task context, typically in a ``finally`` block."""
    _task_id.reset(token)


class RequestIdFilter(logging.Filter):
    """Attach the current request and task IDs to every record that lacks them."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id() or REQUEST_ID_ABSENT
        if not hasattr(record, "task_id"):
            record.task_id = get_task_id() or TASK_ID_ABSENT
        return True


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per line, safe for log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", REQUEST_ID_ABSENT),
            "task_id": getattr(record, "task_id", TASK_ID_ABSENT),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable single-line format for local development."""

    def __init__(self) -> None:
        super().__init__(
            fmt=(
                "%(asctime)s %(levelname)-8s [%(request_id)s task:%(task_id)s] "
                "%(name)s: %(message)s"
            ),
            datefmt="%H:%M:%S",
            defaults={"request_id": REQUEST_ID_ABSENT, "task_id": TASK_ID_ABSENT},
        )
