"""Routes mounted under /api/<version>/.

Handlers should delegate to services; these modules only describe HTTP surface.
"""

from __future__ import annotations

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("workspaces/", include("apps.organizations.urls")),
    path("invitations/", include("apps.organizations.invitation_urls")),
    path("schema/", SpectacularAPIView.as_view(), name="openapi-schema"),
]
