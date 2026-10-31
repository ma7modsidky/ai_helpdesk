"""Configuration for the AI assistant app."""

from __future__ import annotations

from django.apps import AppConfig


class AiAssistantConfig(AppConfig):
    name = "apps.ai_assistant"
    verbose_name = "AI assistant"
    default_auto_field = "django.db.models.BigAutoField"
