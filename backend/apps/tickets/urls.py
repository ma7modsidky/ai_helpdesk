"""Routes under /api/<version>/workspaces/<workspace_id>/tickets/."""

from __future__ import annotations

from django.urls import path

from apps.ai_assistant.views import TicketAIStatusView, TicketDraftView

from .views import (
    TicketAssignView,
    TicketDetailView,
    TicketListCreateView,
    TicketMessageListCreateView,
    TicketTransitionView,
)

urlpatterns = [
    path("", TicketListCreateView.as_view(), name="ticket-list"),
    path("<uuid:ticket_id>/", TicketDetailView.as_view(), name="ticket-detail"),
    path("<uuid:ticket_id>/assign/", TicketAssignView.as_view(), name="ticket-assign"),
    path(
        "<uuid:ticket_id>/transition/",
        TicketTransitionView.as_view(),
        name="ticket-transition",
    ),
    path(
        "<uuid:ticket_id>/messages/",
        TicketMessageListCreateView.as_view(),
        name="ticket-messages",
    ),
    path("<uuid:ticket_id>/ai-draft/", TicketDraftView.as_view(), name="ticket-ai-draft"),
    path("<uuid:ticket_id>/ai-status/", TicketAIStatusView.as_view(), name="ticket-ai-status"),
]
