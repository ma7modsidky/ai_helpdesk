"""Knowledge-base endpoints (T7.1, T7.2).

Authorization follows the ticket routes: ``HasWorkspaceCapability`` resolves the membership and
the view names the capability. Reading articles is a member action; creating, editing,
publishing, archiving, and reindexing require ``articles.manage`` (owner and admin), because
published text is what the AI is allowed to quote to a customer (FR-030).
"""

from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.csrf import enforce_csrf
from apps.common.errors import Conflict
from apps.common.pagination import BoundedPageNumberPagination
from apps.organizations.permissions import HasWorkspaceCapability, workspace_access_for
from apps.organizations.services import Capability, WorkspaceAccess

from .exceptions import ArticleNotFound, ArticleStateConflict
from .models import KnowledgeArticle
from .serializers import (
    ArticleCreateSerializer,
    ArticleListQuerySerializer,
    ArticlePublishSerializer,
    ArticleSerializer,
    ArticleUpdateSerializer,
)
from .services import (
    create_article,
    get_article,
    list_articles,
    request_reindex,
    set_publication,
    update_article,
)

_ARTICLE_MISSING = "The requested article was not found."


def _article_id(kwargs: dict[str, object]) -> UUID:
    """Narrow the URL kwarg; DRF has already validated it as a UUID."""
    return UUID(str(kwargs["article_id"]))


def _article(kwargs: dict[str, object], *, access: WorkspaceAccess) -> KnowledgeArticle:
    try:
        return get_article(access=access, article_id=_article_id(kwargs))
    except ArticleNotFound as exc:
        raise NotFound(_ARTICLE_MISSING) from exc


def _raise_state_conflict(exc: ArticleStateConflict) -> NoReturn:
    raise Conflict(str(exc)) from exc


class ArticleListCreateView(APIView):
    """List the workspace's articles, or create a draft."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    pagination_class = BoundedPageNumberPagination

    @property
    def required_capability(self) -> Capability:
        if self.request.method == "POST":
            return Capability.ARTICLES_MANAGE
        return Capability.ARTICLES_VIEW

    @extend_schema(
        summary="List knowledge articles",
        responses={
            200: ArticleSerializer(many=True),
            400: OpenApiResponse(description="Invalid status filter or search term."),
            404: OpenApiResponse(description="Unknown workspace or no active membership."),
        },
        description=(
            "Paginated, newest activity first. `status` filters on `draft`, `published`, "
            "`archived` (default `all`); `search` matches the title only. Each row reports the "
            "publication state and the indexing job's state, so a screen can show that a "
            "published article is not yet retrievable."
        ),
    )
    def get(self, request: Request, **kwargs: object) -> Response:
        query = ArticleListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        status_filter = query.validated_data.get("status", "all")
        search = query.validated_data.get("search") or None

        access = workspace_access_for(request)
        articles = list_articles(
            access=access,
            status=None if status_filter == "all" else status_filter,
            search=search,
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(articles, request, view=self)
        serializer = ArticleSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        summary="Create a knowledge article",
        request=ArticleCreateSerializer,
        responses={
            201: ArticleSerializer,
            400: OpenApiResponse(description="Invalid title or body."),
            403: OpenApiResponse(
                description="Missing CSRF token, or the role cannot manage articles."
            ),
            404: OpenApiResponse(description="Unknown workspace or no active membership."),
        },
        description=(
            "Creates a `draft`. Nothing is retrievable until the article is published and its "
            "indexing job has succeeded."
        ),
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        form = ArticleCreateSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        access = workspace_access_for(request)

        article = create_article(
            access=access,
            title=form.validated_data["title"].strip(),
            body=form.validated_data["body"],
            author_id=request.user.pk,
        )
        return Response(ArticleSerializer(article).data, status=status.HTTP_201_CREATED)


class ArticleDetailView(APIView):
    """Read or edit one article."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]

    @property
    def required_capability(self) -> Capability:
        if self.request.method == "PATCH":
            return Capability.ARTICLES_MANAGE
        return Capability.ARTICLES_VIEW

    @extend_schema(
        summary="Read a knowledge article",
        responses={
            200: ArticleSerializer,
            404: OpenApiResponse(description="Unknown workspace, membership, or article."),
        },
    )
    def get(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        return Response(ArticleSerializer(_article(kwargs, access=access)).data)

    @extend_schema(
        summary="Edit a knowledge article",
        request=ArticleUpdateSerializer,
        responses={
            200: ArticleSerializer,
            400: OpenApiResponse(description="Empty edit, or a field out of bounds."),
            403: OpenApiResponse(
                description="Missing CSRF token, or the role cannot manage articles."
            ),
            404: OpenApiResponse(description="Unknown workspace, membership, or article."),
        },
        description=(
            "A content change bumps `version`. If the article is published, indexing is queued "
            "for the new version and the stored chunks describe the old text until it "
            "succeeds; the response's `index_status` says which."
        ),
    )
    def patch(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        form = ArticleUpdateSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        access = workspace_access_for(request)
        try:
            article = update_article(
                access=access,
                article_id=_article_id(kwargs),
                title=form.validated_data.get("title"),
                body=form.validated_data.get("body"),
            )
        except ArticleNotFound as exc:
            raise NotFound(_ARTICLE_MISSING) from exc
        return Response(ArticleSerializer(article).data)


class ArticlePublishView(APIView):
    """Publish or archive an article."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.ARTICLES_MANAGE

    @extend_schema(
        summary="Publish or archive a knowledge article",
        request=ArticlePublishSerializer,
        responses={
            200: ArticleSerializer,
            400: OpenApiResponse(description="Unknown lifecycle value."),
            403: OpenApiResponse(description="Missing CSRF token, or the role cannot publish."),
            404: OpenApiResponse(description="Unknown workspace, membership, or article."),
            409: OpenApiResponse(description="The article's current state refuses the change."),
        },
        description=(
            '`{"status": "published"}` publishes and `{"status": "archived"}` archives; '
            "an empty body publishes. Both queue the indexing job. An archived article cannot "
            "be published again without being edited first, and is never retrievable."
        ),
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        form = ArticlePublishSerializer(data=request.data or {})
        form.is_valid(raise_exception=True)
        access = workspace_access_for(request)

        try:
            article = set_publication(
                access=access,
                article_id=_article_id(kwargs),
                status=form.validated_data["status"],
            )
        except ArticleNotFound as exc:
            raise NotFound(_ARTICLE_MISSING) from exc
        except ArticleStateConflict as exc:
            _raise_state_conflict(exc)
        return Response(ArticleSerializer(article).data)


class ArticleReindexView(APIView):
    """Queue indexing again, including after a failure."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.ARTICLES_MANAGE

    @extend_schema(
        summary="Reindex a knowledge article",
        request=None,
        responses={
            202: ArticleSerializer,
            403: OpenApiResponse(
                description="Missing CSRF token, or the role cannot manage articles."
            ),
            404: OpenApiResponse(description="Unknown workspace, membership, or article."),
        },
        description=(
            "Resets the article's indexing job to `pending` and queues it, returning `202`. A "
            "duplicate click does not cost a second job: the worker claims the row once."
        ),
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        access = workspace_access_for(request)
        try:
            article = request_reindex(access=access, article_id=_article_id(kwargs))
        except ArticleNotFound as exc:
            raise NotFound(_ARTICLE_MISSING) from exc
        return Response(ArticleSerializer(article).data, status=status.HTTP_202_ACCEPTED)
