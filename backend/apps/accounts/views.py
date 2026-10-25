"""Session authentication endpoints.

Views stay thin: credential validation is in the serializer, session handling is
Django's, and CSRF is enforced explicitly because DRF views are CSRF-exempt.
"""

from __future__ import annotations

from django.contrib.auth import login as session_login
from django.contrib.auth import logout as session_logout
from django.middleware.csrf import get_token
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.csrf import enforce_csrf

from .authentication import SessionAuthentication
from .serializers import (
    CsrfTokenSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    UserSerializer,
)


class CsrfTokenView(APIView):
    """Issue a CSRF token for the login form.

    The cookie is httpOnly, so JavaScript obtains the value from this response
    body and echoes it in the ``X-CSRFToken`` header on state-changing requests.
    """

    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Fetch a CSRF token",
        responses={200: CsrfTokenSerializer},
        description="Public. Sets the CSRF cookie and returns its value.",
    )
    def get(self, request, **kwargs: object):  # type: ignore[no-untyped-def]
        # ``version`` arrives as a URL kwarg from the /api/<version>/ prefix.
        return Response({"csrf_token": get_token(request)})


class LoginView(APIView):
    """Start a session with email and password."""

    # SessionAuthentication is declared so DRF sees a challenge scheme and keeps
    # failed logins as 401 rather than downgrading them to 403. CSRF is still
    # enforced explicitly below, because an anonymous request has no session to
    # validate against.
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"

    @extend_schema(
        summary="Log in",
        request=LoginSerializer,
        responses={
            200: LoginResponseSerializer,
            401: OpenApiResponse(description="Invalid credentials."),
            403: OpenApiResponse(description="Missing or invalid CSRF token."),
            429: OpenApiResponse(description="Too many attempts."),
        },
        description="Public. Requires a CSRF token from /api/v1/auth/csrf/.",
    )
    def post(self, request, **kwargs: object):  # type: ignore[no-untyped-def]
        enforce_csrf(request)

        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        session_login(request, user)
        # Django rotates the CSRF token on login; return the new value because the
        # cookie is httpOnly and the client cannot read it.
        return Response(
            {"user": UserSerializer(user).data, "csrf_token": get_token(request)},
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """End the current session."""

    @extend_schema(
        summary="Log out",
        request=None,
        responses={204: OpenApiResponse(description="Session ended.")},
    )
    def post(self, request, **kwargs: object):  # type: ignore[no-untyped-def]
        session_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Return the authenticated user."""

    @extend_schema(summary="Current user", responses={200: UserSerializer})
    def get(self, request, **kwargs: object):  # type: ignore[no-untyped-def]
        return Response(UserSerializer(request.user).data)
