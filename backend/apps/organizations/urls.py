"""Routes under /api/<version>/workspaces/."""

from __future__ import annotations

from django.urls import path

from .views import (
    InvitationListCreateView,
    InvitationResendView,
    InvitationRevokeView,
    MemberDetailView,
    MemberListView,
    OwnershipTransferView,
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
    path(
        "<uuid:workspace_id>/transfer-ownership/",
        OwnershipTransferView.as_view(),
        name="workspace-transfer-ownership",
    ),
    path(
        "<uuid:workspace_id>/invitations/",
        InvitationListCreateView.as_view(),
        name="workspace-invitations",
    ),
    path(
        "<uuid:workspace_id>/invitations/<uuid:invitation_id>/",
        InvitationRevokeView.as_view(),
        name="workspace-invitation",
    ),
    path(
        "<uuid:workspace_id>/invitations/<uuid:invitation_id>/resend/",
        InvitationResendView.as_view(),
        name="workspace-invitation-resend",
    ),
]
