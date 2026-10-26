"""Invitee-side invitation routes, mounted under /api/<version>/invitations/.

The token is carried in the JSON body rather than the path so that request logs,
which record the path, never contain a usable invitation.
"""

from __future__ import annotations

from django.urls import path

from .views import InvitationAcceptView, InvitationPreviewView

app_name = "invitations"

urlpatterns = [
    path("preview/", InvitationPreviewView.as_view(), name="preview"),
    path("accept/", InvitationAcceptView.as_view(), name="accept"),
]
