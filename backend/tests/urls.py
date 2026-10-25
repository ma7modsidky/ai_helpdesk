"""Test-only URLconf.

The paginator and the unhandled-error path have no product endpoint yet, so they
are exercised through routes that exist only for tests.
"""

from __future__ import annotations

from typing import NoReturn

from django.http import HttpRequest
from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import BoundedPageNumberPagination

PROBE_ITEM_COUNT = 150


class PaginationProbeView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        paginator = BoundedPageNumberPagination()
        # A list is a valid runtime input for page-number pagination and avoids
        # creating 150 rows just to exercise the bounds; the stub only describes
        # querysets.
        page: list[int] | None = paginator.paginate_queryset(
            list(range(PROBE_ITEM_COUNT)),  # type: ignore[arg-type]
            request,
            view=self,
        )
        return paginator.get_paginated_response(page)


def boom(request: HttpRequest) -> NoReturn:
    raise RuntimeError("boom-should-never-reach-the-client")


# Django resolves error handlers from the active URLconf, so the test URLconf
# must declare them for the 500 path to reach our JSON handler.
handler404 = "apps.common.errors.handler404"
handler500 = "apps.common.errors.handler500"

urlpatterns = [
    path("test-pagination/", PaginationProbeView.as_view(), name="test-pagination"),
    path("test-boom/", boom, name="test-boom"),
]
