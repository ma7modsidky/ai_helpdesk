"""The Celery application.

Rebuilt Celery's configuration from Django's settings under the ``CELERY_`` namespace, so a
deployment has one configuration surface rather than two that can disagree (ADR-032). Tasks
are discovered from ``apps/<app>/tasks.py`` in every installed app, which is why adding an
app needs no registry edit here.

Worker and Beat are separate processes and are started with the same module:

    uv run celery -A config worker --loglevel=info
    uv run celery -A config beat --loglevel=info

Neither is required for the API to serve traffic: ticket creation does not depend on the
queue, and no task is on a request path until T5.2.
"""

from __future__ import annotations

import os

from celery import Celery

from apps.common.tasking import CorrelatedTask

# `manage.py` sets this too; the default keeps `celery -A config ...` usable on its own
# without exporting the variable in every shell.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# The base class is passed to the constructor rather than set as a setting: Celery reads
# `task_cls` from here, not from the settings namespace, so a `CELERY_TASK_CLS` would be
# silently ignored. Every task, including ones added later, inherits the correlation
# context from this one argument.
app = Celery("resolveai", task_cls=CorrelatedTask)

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
