"""HTTP shapes for AI results (T6.3).

The response carries what the contract names — status, draft text, cited sources, provenance —
plus ``error``, which is the exception *class* of a failed attempt and never its message. That
is enough for a UI to offer a retry without showing a customer text or a provider response.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import ReplyDraft, TicketClassification


class SourceArticleSerializer(serializers.Serializer[Any]):
    """One citation: an identifier the client can resolve plus the title to show."""

    article_id = serializers.CharField()
    title = serializers.CharField()


class ReplyDraftSerializer(serializers.ModelSerializer[ReplyDraft]):
    source_articles = SourceArticleSerializer(many=True)
    # Never false: the field exists so a client cannot render the text as a sent reply, and so
    # the contract's guarantee is visible in the payload rather than only in the docs (ADR-002).
    requires_human_approval = serializers.SerializerMethodField()
    error = serializers.SerializerMethodField()

    class Meta:
        model = ReplyDraft
        fields = (
            "id",
            "status",
            "draft_text",
            "source_articles",
            "provider",
            "model",
            "requires_human_approval",
            "error",
            "created_at",
        )
        read_only_fields = fields

    def get_requires_human_approval(self, obj: ReplyDraft) -> bool:
        return True

    def get_error(self, obj: ReplyDraft) -> str | None:
        """The failed attempt's exception class, or null.

        A class name is not sensitive; the message is, which is why the row has never stored it.
        """
        return obj.last_error or None


class ClassificationSerializer(serializers.ModelSerializer[TicketClassification]):
    class Meta:
        model = TicketClassification
        fields = (
            "status",
            "category",
            "sentiment",
            "suggested_priority",
            "confidence",
            "rationale",
            "provider",
            "model",
            "created_at",
        )
        read_only_fields = fields


class AIStatusSerializer(serializers.Serializer[Any]):
    """Everything the AI panel needs, in one read.

    Either half may be null: a ticket has a classification before anyone asks for a draft, and
    an older ticket may have neither.
    """

    classification = ClassificationSerializer(allow_null=True, required=False)
    draft = ReplyDraftSerializer(allow_null=True, required=False)
