"""Workspace and membership endpoints.

Every route under a workspace delegates authorization to
``HasWorkspaceCapability`` and the business rule to ``services``. The handlers
only translate input into service calls and results into responses.
"""

from __future__ import annotations

from typing import NoReturn, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.common.csrf import enforce_csrf
from apps.common.errors import Conflict, InvitationExpiredError
from apps.common.pagination import BoundedPageNumberPagination

from .exceptions import (
    InsufficientRole,
    InvitationAlreadyPending,
    InvitationEmailMismatch,
    InvitationEmailTaken,
    InvitationError,
    InvitationExpired,
    InvitationNotFound,
    InvitationNotPending,
    InvitationRoleNotAllowed,
    LastOwnerRequired,
    MembershipNotFound,
    MembershipRoleConflict,
    OwnershipTargetNotActive,
    OwnershipTransferToSelf,
    WorkspaceSlugTaken,
)
from .invitations import (
    accept_invitation,
    accept_path,
    create_invitation,
    invitation_queryset,
    preview_invitation,
    resend_invitation,
    revoke_invitation,
)
from .models import Invitation, InvitationStatus, Membership, MembershipStatus
from .permissions import HasWorkspaceCapability, workspace_access_for
from .serializers import (
    InvitationAcceptanceSerializer,
    InvitationCreateSerializer,
    InvitationPreviewSerializer,
    InvitationSerializer,
    InvitationTokenSerializer,
    MembershipSerializer,
    MembershipUpdateSerializer,
    OwnershipTransferResultSerializer,
    OwnershipTransferSerializer,
    WorkspaceCreateSerializer,
    WorkspaceSerializer,
)
from .services import (
    Capability,
    accessible_workspaces,
    change_membership,
    create_workspace,
    transfer_ownership,
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


class OwnershipTransferView(APIView):
    """Hand workspace ownership to another active member, atomically.

    ``members.manage`` admits admins so the service can distinguish "not allowed"
    from "not the owner" with one rule; the owner check itself lives in the domain
    service, under the workspace lock.
    """

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.MEMBERS_MANAGE

    @extend_schema(
        summary="Transfer workspace ownership",
        request=OwnershipTransferSerializer,
        responses={
            200: OwnershipTransferResultSerializer,
            400: OpenApiResponse(description="Self-transfer or malformed membership id."),
            403: OpenApiResponse(description="Only the current owner may transfer ownership."),
            404: OpenApiResponse(description="Unknown workspace or membership."),
            409: OpenApiResponse(description="The target membership is not active."),
        },
        description=(
            "The target becomes ``owner`` and the caller ``admin`` in one transaction, so an "
            "active owner always remains."
        ),
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        serializer = OwnershipTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            owner, previous_owner = transfer_ownership(
                access=access,
                membership_id=serializer.validated_data["membership_id"],
            )
        except MembershipNotFound as exc:
            raise NotFound("The requested membership was not found.") from exc
        except InsufficientRole as exc:
            raise PermissionDenied("You do not have access to this resource.") from exc
        except OwnershipTransferToSelf as exc:
            raise ValidationError({"membership_id": ["You already own this workspace."]}) from exc
        except OwnershipTargetNotActive as exc:
            raise Conflict("Only an active member can become the workspace owner.") from exc

        return Response(
            OwnershipTransferResultSerializer(
                {"owner": owner, "previous_owner": previous_owner}
            ).data
        )


def _raise_invitation_error(exc: InvitationError) -> NoReturn:
    """Translate invitation domain failures into the API's error envelope."""
    if isinstance(exc, InvitationNotFound):
        raise NotFound("The requested invitation was not found.") from exc
    if isinstance(exc, InvitationExpired):
        raise InvitationExpiredError from exc
    if isinstance(exc, InvitationAlreadyPending | InvitationNotPending | MembershipRoleConflict):
        raise Conflict(str(exc)) from exc
    if isinstance(exc, InvitationEmailTaken):
        raise ValidationError(
            {"email": ["This address is already a member of this workspace."]}
        ) from exc
    if isinstance(exc, InvitationRoleNotAllowed):
        raise ValidationError({"role": ["An invitation cannot grant the owner role."]}) from exc
    if isinstance(exc, InvitationEmailMismatch):
        raise PermissionDenied("You do not have access to this resource.") from exc
    raise exc


def _invitation_response(invitation: Invitation, token: str, *, created: bool) -> Response:
    """Invitation representation plus the one-time accept path."""
    payload = dict(InvitationSerializer(invitation).data)
    payload["accept_path"] = accept_path(token)
    return Response(
        payload,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


class InvitationListCreateView(APIView):
    """List invitations for a workspace, or issue one."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.MEMBERS_MANAGE
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_create"

    def get_throttles(self) -> list[BaseThrottle]:
        # Only issuing and resending are rate limited; browsing is cheap.
        if self.request.method == "POST":
            return super().get_throttles()
        return []

    @extend_schema(
        summary="List workspace invitations",
        responses={
            200: InvitationSerializer(many=True),
            403: OpenApiResponse(description="Only owners and admins may see invitations."),
            404: OpenApiResponse(description="Unknown workspace or no active membership."),
        },
        description="Paginated. The token is never returned by a read.",
    )
    def get(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        status_filter = request.query_params.get("status", InvitationStatus.PENDING.value)
        allowed = {*InvitationStatus.values, "all"}
        if status_filter not in allowed:
            raise ValidationError({"status": ["Unknown invitation status."]})

        queryset = invitation_queryset(access.workspace, status_filter)
        paginator = BoundedPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self) or []
        return paginator.get_paginated_response(InvitationSerializer(page, many=True).data)

    @extend_schema(
        summary="Invite a member",
        request=InvitationCreateSerializer,
        responses={
            201: InvitationSerializer,
            400: OpenApiResponse(
                description="Invalid email, unknown role, owner role, or an existing member."
            ),
            403: OpenApiResponse(description="Only owners and admins may invite."),
            404: OpenApiResponse(description="Unknown workspace or no active membership."),
            409: OpenApiResponse(description="A pending invitation already exists."),
        },
        description="The response carries ``accept_path`` once; delivery is best effort.",
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            invitation, token = create_invitation(
                workspace=access.workspace,
                inviter=cast(User, request.user),
                email=serializer.validated_data["email"],
                role=serializer.validated_data["role"],
            )
        except InvitationError as exc:
            _raise_invitation_error(exc)

        return _invitation_response(invitation, token, created=True)


class InvitationResendView(APIView):
    """Rotate an invitation's token and try delivery again."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.MEMBERS_MANAGE
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_create"

    @extend_schema(
        summary="Resend an invitation",
        request=None,
        responses={
            200: InvitationSerializer,
            403: OpenApiResponse(description="Only owners and admins may resend."),
            404: OpenApiResponse(description="Unknown workspace or invitation."),
            409: OpenApiResponse(description="The invitation is accepted or revoked."),
        },
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        try:
            invitation, token = resend_invitation(
                workspace=access.workspace,
                invitation_id=cast(UUID, kwargs["invitation_id"]),
            )
        except InvitationError as exc:
            _raise_invitation_error(exc)

        return _invitation_response(invitation, token, created=False)


class InvitationRevokeView(APIView):
    """Cancel a pending invitation."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.MEMBERS_MANAGE

    @extend_schema(
        summary="Revoke an invitation",
        responses={
            204: OpenApiResponse(description="Revoked, or already revoked."),
            403: OpenApiResponse(description="Only owners and admins may revoke."),
            404: OpenApiResponse(description="Unknown workspace or invitation."),
            409: OpenApiResponse(description="The invitation was already accepted."),
        },
    )
    def delete(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        try:
            revoke_invitation(
                workspace=access.workspace,
                invitation_id=cast(UUID, kwargs["invitation_id"]),
            )
        except InvitationError as exc:
            _raise_invitation_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationPreviewView(APIView):
    """Public preview of an invitation, authorized by its token."""

    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_accept"

    @extend_schema(
        summary="Preview an invitation",
        request=InvitationTokenSerializer,
        responses={
            200: InvitationPreviewSerializer,
            404: OpenApiResponse(description="Unknown invitation, or an archived workspace."),
        },
        description=(
            "Public. The token travels in the body, so it never appears in a request log."
        ),
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        serializer = InvitationTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            invitation = preview_invitation(token=serializer.validated_data["token"])
        except InvitationError as exc:
            _raise_invitation_error(exc)
        return Response(InvitationPreviewSerializer(invitation).data)


class InvitationAcceptView(APIView):
    """Accept an invitation as the signed-in account with the invited address."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_accept"

    @extend_schema(
        summary="Accept an invitation",
        request=InvitationTokenSerializer,
        responses={
            200: InvitationAcceptanceSerializer,
            401: OpenApiResponse(description="No session."),
            403: OpenApiResponse(description="Missing CSRF token, or the address does not match."),
            404: OpenApiResponse(description="Unknown or revoked invitation."),
            409: OpenApiResponse(description="Expired, or an existing role conflict."),
        },
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        serializer = InvitationTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            workspace, membership = accept_invitation(
                user=cast(User, request.user),
                token=serializer.validated_data["token"],
            )
        except InvitationError as exc:
            _raise_invitation_error(exc)

        return Response(
            InvitationAcceptanceSerializer({"workspace": workspace, "membership": membership}).data
        )
