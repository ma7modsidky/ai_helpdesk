"""Project configuration package.

Importing the Celery application here is what makes ``celery -A config`` find it: the
package is imported before Django's settings module resolves, and any process that loads
Django therefore has the app registered. It also means the shared ``task_cls`` and the
settings namespace apply to every task without per-module setup.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
