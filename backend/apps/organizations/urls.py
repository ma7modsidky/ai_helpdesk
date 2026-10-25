"""Routes under /api/<version>/workspaces/."""

from __future__ import annotations

from django.urls import path

from .views import (
    MemberDetailView,
    MemberListView,
    WorkspaceListCreateView,
)

urlpatterns = [
    path("", WorkspaceListCreateView.as_view(), name="workspace-list"),
    path(
        "<uuid:workspace_id>/members/",
        MemberListView.as_view(),
        name="workspace-members",
    ),
    path(
        "<uuid:workspace_id>/members/<uuid:membership_id>/",
        MemberDetailView.as_view(),
        name="workspace-member",
    ),
]
