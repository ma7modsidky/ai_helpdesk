"""Factories for background-task tests.

A record's identity is its ``(task_name, idempotency_key)`` pair, so the defaults name the
simulated task and give each row a distinct key; a test that cares about a status asks for it.
"""

from __future__ import annotations

import factory
from factory.declarations import Sequence

from apps.common.models import TaskRecord


class TaskRecordFactory(factory.django.DjangoModelFactory[TaskRecord]):
    class Meta:
        model = TaskRecord

    task_name = "apps.common.tasks.simulate_work"
    idempotency_key = Sequence(  # type: ignore[no-untyped-call]
        lambda index: f"task-key-{index}"
    )
