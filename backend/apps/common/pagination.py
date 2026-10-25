"""List pagination with a hard upper bound.

Page numbers are 1-based; clients may request a smaller or larger page with
``?page_size=`` but can never exceed the maximum, which keeps list endpoints from
being turned into unbounded exports.
"""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class BoundedPageNumberPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"
