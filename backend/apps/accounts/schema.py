"""OpenAPI description of the session authentication scheme.

Our ``SessionAuthentication`` subclasses DRF's, so drf-spectacular cannot infer a
security scheme for it and would silently omit auth from the schema.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension


# drf-spectacular ships no stubs for its extension base class.
class SessionAuthenticationScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    target_class = "apps.accounts.authentication.SessionAuthentication"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, str]:
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": settings.SESSION_COOKIE_NAME,
        }
