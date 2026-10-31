"""AI endpoints: draft generation and job status (T6.3).

Authorization is resolved once by ``HasWorkspaceCapability`` and the ticket is loaded through
the tenant-scoped ticket service, so an id from another workspace is a 404 before any AI row is
written. A draft is queued, never generated inline: a model call behind a request would hold a
worker-sized slot for seconds and turn a provider outage into a slow endpoint.
"""

from __future__ import annotations

from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.csrf import enforce_csrf
from apps.organizations.permissions import HasWorkspaceCapability, workspace_access_for
from apps.organizations.services import Capability, WorkspaceAccess
from apps.tickets.exceptions import TicketNotFound
from apps.tickets.models import Ticket
from apps.tickets.services import get_ticket

from .drafts import latest_classification, latest_draft, request_draft
from .serializers import AIStatusSerializer, ReplyDraftSerializer

_TICKET_MISSING = "The requested ticket was not found."


def _ticket_id(kwargs: dict[str, object]) -> UUID:
    """Narrow the URL kwarg; DRF has already validated it as a UUID."""
    return UUID(str(kwargs["ticket_id"]))


def _ticket(kwargs: dict[str, object], *, access: WorkspaceAccess) -> Ticket:
    """Load the ticket through the tenant-scoped service, or raise 404."""
    try:
        return get_ticket(access=access, ticket_id=_ticket_id(kwargs))
    except TicketNotFound as exc:
        raise NotFound(_TICKET_MISSING) from exc


class TicketDraftView(APIView):
    """Queue a reply draft for a ticket. It never sends anything."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    # Drafting exists to produce a reply, so it takes the same capability as replying. The send
    # itself is still a separate request to the message endpoint (ADR-002).
    required_capability = Capability.TICKETS_COMMENT
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai_generation"

    @extend_schema(
        summary="Generate a reply draft",
        request=None,
        responses={
            202: ReplyDraftSerializer,
            403: OpenApiResponse(description="Missing CSRF token, or insufficient role."),
            404: OpenApiResponse(description="Unknown workspace, membership, or ticket."),
            429: OpenApiResponse(description="Too many drafts requested by this client."),
        },
        description=(
            "Queues one draft for the ticket's current version and returns `202` with the job. "
            "A second request while a draft is still pending or running returns that job rather "
            "than paying for another. Nothing is published: `POST .../messages/` remains the only "
            "way to send a reply, and the response always says human approval is required."
        ),
    )
    def post(self, request: Request, **kwargs: object) -> Response:
        enforce_csrf(request)
        access = workspace_access_for(request)
        try:
            job = request_draft(access=access, ticket_id=_ticket_id(kwargs))
        except TicketNotFound as exc:
            raise NotFound(_TICKET_MISSING) from exc

        return Response(ReplyDraftSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class TicketAIStatusView(APIView):
    """Read the latest classification and draft for a ticket."""

    permission_classes = [IsAuthenticated, HasWorkspaceCapability]
    required_capability = Capability.TICKETS_VIEW

    @extend_schema(
        summary="Read AI job status",
        responses={
            200: AIStatusSerializer,
            404: OpenApiResponse(description="Unknown workspace, membership, or ticket."),
        },
        description=(
            "Returns the newest classification and the newest draft for this ticket, each with "
            "its job status (`pending`, `running`, `succeeded`, `failed`) so a client can poll "
            "with a bound instead of guessing. Either half may be null."
        ),
    )
    def get(self, request: Request, **kwargs: object) -> Response:
        access = workspace_access_for(request)
        ticket = _ticket(kwargs, access=access)
        payload = {
            "classification": latest_classification(ticket),
            "draft": latest_draft(ticket),
        }
        return Response(AIStatusSerializer(instance=payload).data)
