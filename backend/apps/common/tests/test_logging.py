from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from apps.common.logging import (
    REQUEST_ID_ABSENT,
    ConsoleFormatter,
    JsonFormatter,
    RequestIdFilter,
    get_request_id,
    reset_request_id,
    set_request_id,
)

BACKEND_DIR = Path(__file__).resolve().parents[3]


def _make_record(message: str, *, exc_info: object = None) -> logging.LogRecord:
    return logging.LogRecord(
        name="apps.common.demo",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,  # type: ignore[arg-type]
    )


def _run_settings_import(overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_", "POSTGRES_"))
    }
    env.update(overrides)
    env["PYTHONPATH"] = str(BACKEND_DIR)

    return subprocess.run(
        [sys.executable, "-c", "import config.settings.base"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_filter_attaches_current_request_id() -> None:
    record = _make_record("hello")
    token = set_request_id("request-123")
    try:
        RequestIdFilter().filter(record)
    finally:
        reset_request_id(token)

    assert record.request_id == "request-123"


def test_filter_marks_absent_request_id() -> None:
    record = _make_record("hello")

    assert get_request_id() is None
    RequestIdFilter().filter(record)

    assert record.request_id == REQUEST_ID_ABSENT


def test_filter_does_not_overwrite_explicit_request_id() -> None:
    record = _make_record("hello")
    record.request_id = "explicit"  # type: ignore[attr-defined]

    RequestIdFilter().filter(record)

    assert record.request_id == "explicit"


def test_json_formatter_emits_single_line_with_required_keys() -> None:
    record = _make_record("ticket created")
    record.request_id = "abc123"  # type: ignore[attr-defined]

    output = JsonFormatter().format(record)

    assert "\n" not in output
    payload = json.loads(output)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "apps.common.demo"
    assert payload["message"] == "ticket created"
    assert payload["request_id"] == "abc123"
    assert payload["timestamp"].endswith("+00:00")


def test_json_formatter_escapes_embedded_newlines() -> None:
    record = _make_record("first line\nsecond line")
    record.request_id = "abc123"  # type: ignore[attr-defined]

    output = JsonFormatter().format(record)

    assert "\n" not in output
    assert json.loads(output)["message"] == "first line\nsecond line"


def test_json_formatter_includes_exception_text() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record("failed", exc_info=sys.exc_info())
    record.request_id = "abc123"  # type: ignore[attr-defined]

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]


def test_json_formatter_uses_placeholder_without_request_context() -> None:
    payload = json.loads(JsonFormatter().format(_make_record("no context")))

    assert payload["request_id"] == REQUEST_ID_ABSENT


def test_console_formatter_includes_request_id() -> None:
    record = _make_record("console line")
    record.request_id = "req-9"  # type: ignore[attr-defined]

    assert "req-9" in ConsoleFormatter().format(record)


def test_console_formatter_defaults_when_attribute_missing() -> None:
    assert REQUEST_ID_ABSENT in ConsoleFormatter().format(_make_record("bare"))


def test_invalid_log_format_is_rejected() -> None:
    result = _run_settings_import({"DJANGO_LOG_FORMAT": "xml"})

    assert result.returncode != 0
    assert "DJANGO_LOG_FORMAT" in result.stderr


def test_invalid_log_level_is_rejected() -> None:
    result = _run_settings_import({"DJANGO_LOG_LEVEL": "LOUD"})

    assert result.returncode != 0
    assert "DJANGO_LOG_LEVEL" in result.stderr


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_valid_log_format_is_accepted(log_format: str) -> None:
    result = _run_settings_import({"DJANGO_LOG_FORMAT": log_format, "DJANGO_LOG_LEVEL": "debug"})

    assert result.returncode == 0, result.stderr
