"""The ``task_status`` command: operator visibility without a broker (T5.4)."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.common.models import TaskRecord, TaskStatus

pytestmark = pytest.mark.django_db

TASK_NAME = "apps.common.tasks.simulate_work"


def _stuck_record() -> TaskRecord:
    record = TaskRecord.objects.create(task_name=TASK_NAME, idempotency_key="stuck")
    TaskRecord.objects.filter(pk=record.pk).update(
        status=TaskStatus.RUNNING,
        started_at=timezone.now() - timedelta(hours=2),
        attempts=1,
    )
    return record


def test_reports_counts_and_finds_stuck_work() -> None:
    _stuck_record()
    out = StringIO()

    call_command("task_status", stdout=out)

    text = out.getvalue()
    assert "running: 1" in text
    assert "stuck running (>15m): 1" in text
    assert "the worker may have died mid-task" in text


def test_fails_when_stuck_work_exists_and_the_flag_is_set() -> None:
    _stuck_record()

    with pytest.raises(CommandError):
        call_command("task_status", "--fail-on-stuck", stdout=StringIO())


def test_passes_when_work_is_moving() -> None:
    out = StringIO()

    call_command("task_status", "--fail-on-stuck", stdout=out)

    assert "stuck running: 0" in out.getvalue()


def test_rejects_a_non_positive_stale_window() -> None:
    with pytest.raises(CommandError):
        call_command("task_status", "--stale-minutes", "0", stdout=StringIO())
