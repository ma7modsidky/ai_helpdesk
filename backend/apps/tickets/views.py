"""Ticket, command, and conversation endpoints.

Authorization is resolved once by ``HasWorkspaceCapability`` and handed to the
service layer; the handlers only choose a capability, validate shape, and translate
domain failures into the contract's status codes. Anything that decides whether a
change is legal lives in ``services``.
"""

from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.csrf import enforce_csrf
from apps.common.errors import Conflict, VersionConflict
from apps.common.pagination import BoundedPageNumberPagination
from apps.organizations.exceptions import InsufficientRole
from apps.organizations.permissions import HasWorkspaceCapability, workspace_access_for
from apps.organizations.services import Capability

from .exceptions import (
    IllegalTransition,
    InvalidAssignee,
    InvalidRequester,
    TicketError,
    TicketNotFound,
    TicketVersionConflict,
)
from .models import TicketPriority
from .serializers import (
    TicketAssignSerializer,
    TicketCreateSerializer,
    TicketListQuerySerializer,
    TicketMessageCreateSerializer,
    TicketMessageSerializer,
    TicketSerializer,
    TicketTransitionSerializer,
    TicketUpdateSerializer,
)
from .services import (
    add_message,
    assign_ticket,
    create_ticket,
    get_ticket,
    list_messages,
    list_tickets,
    transition_ticket,
    update_ticket_fields,
)


def _correlation_id(request: Request) -> str:
    """The request's correlation id, so audit rows join the access log."""
    return str(getattr(request._request, "request_id", "") or "")


def _if_match_version(request: Request) -> int | None:
    """Parse ``If-Match: "<version>"``, returning ``None`` if it is unusable.

    Accepts the quoted strong form the contract documents, an unquoted integer, and
    a weak ``W/`` prefix, because proxies and HTTP clients differ on quoting. A
    value that is missing or not an integer is handled as a conflict by the caller:
    the client cannot be allowed to write without naming the version it read.
    """
    raw = request.headers.get("If-Match")
    if not raw:
        return None
    value = raw.strip()
    if value.startswith("W/"):
        value = value[2:].strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if not value.isdigit():
        return None
    return int(value)


def _raise_ticket_error(exc: TicketError) -> NoReturn:
    """Translate a domain refusal into the API's error envelope."""
    if isinstance(exc, TicketNotFound):
        raise NotFound("The requested ticket was not found.") from exc
    if isinstance(exc, TicketVersionConflict):
        raise VersionConflict(current_version=exc.current_version) from exc
    if isinstance(exc, InvalidRequester):
        raise ValidationError({"requester_user_id": [str(exc)]}) from exc
    if isinstance(exc, InvalidAssignee):
        raise ValidationError({"assignee_id": [str(exc)]}) from exc
    if isinstance(exc, IllegalTransition):
        raise Conflict(str(exc)) from exc
    raise exc


class TicketListCreateView(APIView):
    """List or create tickets in a workspace."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ticket_create"

    @property
    def required_capability(self) -> Capability:
        # Reading and creating are separate capabilities even though every role
        # holds both today; that keeps a future read-only role a matrix edit.
        if self.request.method == "POST":
            return Capability.TICKETS_CREATE
        return Capability.TICKETS_VIEW

    def get_throttles(self) -> list[BaseThrottle]:
        # Only creation adds rows on demand; the inbox must stay usable.
        if self.request.method == "POST":
            return super().get_throttles()
        return []

    @extend_schema(
        summary="List tickets",
        responses={
            200: TicketSerializer(many=True),
            400: OpenApiResponse(description="Invalid filter, search, or ordering value."),
            404: OpenApiResponse(description="Unknown workspace or no active membership."),
        },
        description=(
            "Paginated, workspace-wide. Filters combine with AND; ``assignee`` accepts "
            "``me``, ``unassigned``, or a user id; ordering is allowlisted."
        ),
    )
    def get(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        params = TicketListQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        query = params.validated_data

        queryset = list_tickets(
            access=access,
            status=query.get("status"),
            priority=query.get("priority"),
            assignee=query.get("assignee"),
            search=query.get("search"),
            ordering=query.get("ordering"),
        )
        paginator = BoundedPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self) or []
        return paginator.get_paginated_response(TicketSerializer(page, many=True).data)

    @extend_schema(
        summary="Create a ticket",
        request=TicketCreateSerializer,
        responses={
            201: TicketSerializer,
            400: OpenApiResponse(
                description="Invalid input, or a requester who is not an active member."
            ),
            403: OpenApiResponse(description="Missing CSRF token, or insufficient role."),
            404: OpenApiResponse(description="Unknown workspace or no active membership."),
            429: OpenApiResponse(description="Too many tickets created by this client."),
        },
        description=(
            "New tickets are always ``open`` and unassigned; status and assignment have "
            "their own commands."
        ),
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        access = workspace_access_for(request)
        serializer = TicketCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            ticket = create_ticket(
                access=access,
                subject=data["subject"],
                description=data["description"],
                requester_email=data["requester_email"],
                requester_name=data.get("requester_name", ""),
                requester_user_id=data.get("requester_user_id"),
                priority=data.get("priority", TicketPriority.NORMAL.value),
                category=data.get("category", ""),
                correlation_id=_correlation_id(request),
            )
        except TicketError as exc:
            _raise_ticket_error(exc)

        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


class TicketDetailView(APIView):
    """Read a ticket, or edit its fields with ``If-Match``."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]

    @property
    def required_capability(self) -> Capability:
        if self.request.method == "PATCH":
            return Capability.TICKETS_EDIT
        return Capability.TICKETS_VIEW

    @extend_schema(
        summary="Retrieve a ticket",
        responses={
            200: TicketSerializer,
            404: OpenApiResponse(description="Unknown workspace, membership, or ticket."),
        },
    )
    def get(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        try:
            ticket = get_ticket(access=access, ticket_id=_ticket_id(kwargs))
        except TicketError as exc:
            _raise_ticket_error(exc)
        return Response(TicketSerializer(ticket).data)

    @extend_schema(
        summary="Edit ticket fields",
        request=TicketUpdateSerializer,
        responses={
            200: TicketSerializer,
            400: OpenApiResponse(description="A field that cannot be edited, or no fields."),
            404: OpenApiResponse(description="Unknown workspace, membership, or ticket."),
            409: OpenApiResponse(
                description="Missing or stale ``If-Match``; ``error.details.version`` is current."
            ),
        },
        description=(
            'Requires ``If-Match: "<version>"``. The check and the increment are one '
            "statement, so a stale edit can never overwrite a newer one."
        ),
    )
    def patch(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        access = workspace_access_for(request)
        serializer = TicketUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ticket_id = _ticket_id(kwargs)
        try:
            ticket = get_ticket(access=access, ticket_id=ticket_id)
        except TicketError as exc:
            _raise_ticket_error(exc)

        expected_version = _if_match_version(request)
        if expected_version is None or expected_version != ticket.version:
            raise VersionConflict(current_version=ticket.version)

        try:
            updated = update_ticket_fields(
                access=access,
                ticket_id=ticket_id,
                fields=dict(serializer.validated_data),
                expected_version=expected_version,
                correlation_id=_correlation_id(request),
            )
        except TicketError as exc:
            _raise_ticket_error(exc)

        return Response(TicketSerializer(updated).data)


class TicketAssignView(APIView):
    """Assign the ticket to an active member, or release it."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.TICKETS_ASSIGN_SELF

    @extend_schema(
        summary="Assign a ticket",
        request=TicketAssignSerializer,
        responses={
            200: TicketSerializer,
            400: OpenApiResponse(description="The assignee is not an active member."),
            403: OpenApiResponse(description="An agent acting on someone else's assignment."),
            404: OpenApiResponse(description="Unknown workspace, membership, or ticket."),
        },
        description=(
            "Takes a row lock and returns the updated ticket with its new version. "
            "Idempotent: assigning the current holder again changes nothing."
        ),
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        access = workspace_access_for(request)
        serializer = TicketAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ticket = assign_ticket(
                access=access,
                ticket_id=_ticket_id(kwargs),
                assignee_id=serializer.validated_data["assignee_id"],
                correlation_id=_correlation_id(request),
            )
        except InsufficientRole as exc:
            raise PermissionDenied("You do not have access to this resource.") from exc
        except TicketError as exc:
            _raise_ticket_error(exc)

        return Response(TicketSerializer(ticket).data)


class TicketTransitionView(APIView):
    """Move a ticket between statuses through the documented transitions."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.TICKETS_TRANSITION

    @extend_schema(
        summary="Change a ticket's status",
        request=TicketTransitionSerializer,
        responses={
            200: TicketSerializer,
            400: OpenApiResponse(description="Unknown status."),
            404: OpenApiResponse(description="Unknown workspace, membership, or ticket."),
            409: OpenApiResponse(
                description="Illegal transition from the current status, or a closed ticket."
            ),
        },
        description=(
            "Legality lives in the domain service: agents may resolve, only managers and "
            "above may reopen, and ``closed`` is terminal."
        ),
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        access = workspace_access_for(request)
        serializer = TicketTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ticket = transition_ticket(
                access=access,
                ticket_id=_ticket_id(kwargs),
                status=serializer.validated_data["status"],
                correlation_id=_correlation_id(request),
            )
        except TicketError as exc:
            _raise_ticket_error(exc)

        return Response(TicketSerializer(ticket).data)


class TicketMessageListCreateView(APIView):
    """Read the conversation, or append a reply or internal note."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]

    @property
    def required_capability(self) -> Capability:
        if self.request.method == "POST":
            return Capability.TICKETS_COMMENT
        return Capability.TICKETS_VIEW

    @extend_schema(
        summary="List ticket messages",
        responses={
            200: TicketMessageSerializer(many=True),
            404: OpenApiResponse(description="Unknown workspace, membership, or ticket."),
        },
        description=(
            "Paginated, oldest first. Both visibilities are returned: there is no "
            "customer-facing reader in MVP, and the field is enforced where one exists."
        ),
    )
    def get(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        try:
            queryset = list_messages(access=access, ticket_id=_ticket_id(kwargs))
        except TicketError as exc:
            _raise_ticket_error(exc)

        paginator = BoundedPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self) or []
        return paginator.get_paginated_response(TicketMessageSerializer(page, many=True).data)

    @extend_schema(
        summary="Post a message",
        request=TicketMessageCreateSerializer,
        responses={
            201: TicketMessageSerializer,
            400: OpenApiResponse(description="Empty or over-long body, or unknown visibility."),
            404: OpenApiResponse(description="Unknown workspace, membership, or ticket."),
        },
        description=(
            "Appending a message moves the ticket's ``updated_at`` but not its "
            "``version``, so a reply never invalidates a held field edit."
        ),
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        access = workspace_access_for(request)
        serializer = TicketMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            message = add_message(
                access=access,
                ticket_id=_ticket_id(kwargs),
                body=serializer.validated_data["body"],
                visibility=serializer.validated_data["visibility"],
                correlation_id=_correlation_id(request),
            )
        except TicketError as exc:
            _raise_ticket_error(exc)

        return Response(TicketMessageSerializer(message).data, status=status.HTTP_201_CREATED)


def _ticket_id(kwargs: dict[str, object]) -> UUID:
    """Narrow the URL kwarg; DRF has already validated it as a UUID."""
    return UUID(str(kwargs["ticket_id"]))
