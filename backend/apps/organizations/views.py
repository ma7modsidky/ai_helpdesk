"""Workspace and membership endpoints.

Every route under a workspace delegates authorization to
``HasWorkspaceCapability`` and the business rule to ``services``. The handlers
only translate input into service calls and results into responses.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.common.errors import Conflict
from apps.common.pagination import BoundedPageNumberPagination

from .exceptions import (
    InsufficientRole,
    LastOwnerRequired,
    MembershipNotFound,
    WorkspaceSlugTaken,
)
from .models import Membership, MembershipStatus
from .permissions import HasWorkspaceCapability, workspace_access_for
from .serializers import (
    MembershipSerializer,
    MembershipUpdateSerializer,
    WorkspaceCreateSerializer,
    WorkspaceSerializer,
)
from .services import (
    Capability,
    accessible_workspaces,
    change_membership,
    create_workspace,
)


class WorkspaceListCreateView(APIView):
    """List the workspaces the caller belongs to, or create one."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List workspaces",
        responses={200: WorkspaceSerializer(many=True)},
        description="Paginated. Only active workspaces with an active membership of the caller.",
    )
    def get(self, request: Request, **kwargs: object) -> Response:
        queryset = accessible_workspaces(cast(User, request.user))
        paginator = BoundedPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self) or []
        return paginator.get_paginated_response(WorkspaceSerializer(page, many=True).data)

    @extend_schema(
        summary="Create a workspace",
        request=WorkspaceCreateSerializer,
        responses={
            201: WorkspaceSerializer,
            400: OpenApiResponse(description="Invalid or duplicate slug, or malformed input."),
        },
        description="The authenticated caller becomes the workspace owner.",
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        serializer = WorkspaceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            workspace = create_workspace(
                owner=cast(User, request.user),
                name=data["name"],
                slug=data["slug"],
                timezone=data.get("timezone", "UTC"),
            )
        except WorkspaceSlugTaken as exc:
            # Same envelope and field shape as the serializer's uniqueness check,
            # so a client cannot tell a lost race from an eagerly rejected slug.
            raise ValidationError({"slug": ["This slug is already taken."]}) from exc
        return Response(WorkspaceSerializer(workspace).data, status=status.HTTP_201_CREATED)


class MemberListView(APIView):
    """List the active members of a workspace the caller belongs to."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.MEMBERS_VIEW

    @extend_schema(
        summary="List workspace members",
        responses={
            200: MembershipSerializer(many=True),
            404: OpenApiResponse(description="Unknown workspace or no active membership."),
        },
    )
    def get(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        queryset = (
            Membership.objects.filter(
                workspace=access.workspace,
                status=MembershipStatus.ACTIVE,
            )
            .select_related("user")
            .order_by("created_at", "id")
        )
        paginator = BoundedPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self) or []
        return paginator.get_paginated_response(MembershipSerializer(page, many=True).data)


class MemberDetailView(APIView):
    """Change a member's role or revoke their access."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.MEMBERS_MANAGE

    @extend_schema(
        summary="Update a workspace member",
        request=MembershipUpdateSerializer,
        responses={
            200: MembershipSerializer,
            400: OpenApiResponse(description="Unknown role/status, or an empty update."),
            403: OpenApiResponse(description="The caller's role is too low for this change."),
            404: OpenApiResponse(description="Unknown workspace or membership."),
            409: OpenApiResponse(description="The change would leave no active owner."),
        },
    )
    def patch(self, request: Request, **kwargs: object) -> Response:
        membership_id = cast(UUID, kwargs["membership_id"])
        access = workspace_access_for(request)

        serializer = MembershipUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            membership = change_membership(
                access=access,
                membership_id=membership_id,
                **serializer.validated_data,
            )
        except MembershipNotFound as exc:
            raise NotFound("The requested membership was not found.") from exc
        except InsufficientRole as exc:
            raise PermissionDenied("You do not have access to this resource.") from exc
        except LastOwnerRequired as exc:
            raise Conflict("A workspace must keep at least one active owner.") from exc

        return Response(MembershipSerializer(membership).data)
