"""Session authentication with an explicit challenge header.

DRF converts "not authenticated" into 403 when the authenticator cannot provide a
``WWW-Authenticate`` challenge, which would make unauthenticated and forbidden
indistinguishable to clients. Declaring a scheme keeps them separate: 401 means
"log in", 403 means "authenticated but not allowed".
"""

from __future__ import annotations

from rest_framework.authentication import SessionAuthentication as DRFSessionAuthentication


class SessionAuthentication(DRFSessionAuthentication):
    def authenticate_header(self, request) -> str:  # type: ignore[no-untyped-def]
        # Any non-empty scheme keeps DRF at 401. The scheme name is informational;
        # browsers only prompt for "Basic"/"Digest", so this does not open a dialog.
        return "Session"
