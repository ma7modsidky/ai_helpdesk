"""Configuration for the shared-primitives app.

Installed for its middleware, error handling, logging, and tasks rather than for models, but a
task module is only discovered in an installed app, so `apps.common` is registered and this
class names it explicitly instead of relying on Django's implicit default.
"""

from __future__ import annotations

from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = "apps.common"
    verbose_name = "Shared primitives"
    default_auto_field = "django.db.models.BigAutoField"
