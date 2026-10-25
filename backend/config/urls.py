"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

from apps.common import health

# Every error an API client can receive is JSON, including routing misses and
# unhandled exceptions, so clients never have to parse an HTML error page.
handler404 = "apps.common.errors.handler404"
handler500 = "apps.common.errors.handler500"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live/", health.liveness, name="health-live"),
    path("health/ready/", health.readiness, name="health-ready"),
    path("api/<version>/", include("apps.api.urls")),
]
