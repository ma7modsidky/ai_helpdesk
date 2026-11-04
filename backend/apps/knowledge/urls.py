"""Routes under /api/<version>/workspaces/<workspace_id>/articles/."""

from __future__ import annotations

from django.urls import path

from .views import (
    ArticleDetailView,
    ArticleListCreateView,
    ArticlePublishView,
    ArticleReindexView,
)

urlpatterns = [
    path("", ArticleListCreateView.as_view(), name="article-list"),
    path("<uuid:article_id>/", ArticleDetailView.as_view(), name="article-detail"),
    path("<uuid:article_id>/publish/", ArticlePublishView.as_view(), name="article-publish"),
    path("<uuid:article_id>/reindex/", ArticleReindexView.as_view(), name="article-reindex"),
]
