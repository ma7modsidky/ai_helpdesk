"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.urls import path

from apps.common import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live/", health.liveness, name="health-live"),
    path("health/ready/", health.readiness, name="health-ready"),
]
