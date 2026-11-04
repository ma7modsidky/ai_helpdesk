from __future__ import annotations

from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    """Articles, their chunks, and the indexing job (T7.1, T7.2).

    Installed so Celery discovers ``tasks.index_article``: task autodiscovery walks the
    installed apps, and a module outside them is invisible to a worker (T5.1).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.knowledge"
