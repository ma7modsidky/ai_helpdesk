"""HTTP shapes for the knowledge base (T7.1, T7.2).

The article representation carries both states a reader needs: the publication lifecycle and
the indexing job, including its last error class and the number of chunks retrieval would see.
A published article with a failed job is exactly the case an editor has to notice, so it must
be visible in the payload rather than inferred from a separate call.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import BODY_MAX, TITLE_MAX, ArticleStatus, KnowledgeArticle


class ArticleSerializer(serializers.ModelSerializer[KnowledgeArticle]):
    chunk_count = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeArticle
        fields = (
            "id",
            "title",
            "body",
            "status",
            "version",
            "author_id",
            "published_at",
            "archived_at",
            "index_status",
            "indexed_version",
            "index_attempts",
            "index_error",
            "indexed_at",
            "chunk_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_chunk_count(self, obj: KnowledgeArticle) -> int:
        """Chunks of the current version.

        The list view annotates this, so a page costs one query; the detail view counts, which
        is one extra query for one row.
        """
        annotated = getattr(obj, "chunk_count", None)
        if isinstance(annotated, int):
            return annotated
        return obj.chunks.filter(article_version=obj.version).count()


class ArticleCreateSerializer(serializers.Serializer[Any]):
    title = serializers.CharField(max_length=TITLE_MAX)
    body = serializers.CharField(max_length=BODY_MAX)


class ArticleUpdateSerializer(serializers.Serializer[Any]):
    """A partial edit. At least one field is required, and an empty body is refused."""

    title = serializers.CharField(max_length=TITLE_MAX, required=False)
    body = serializers.CharField(max_length=BODY_MAX, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs:
            raise serializers.ValidationError("Provide a title, a body, or both.")
        return attrs


class ArticlePublishSerializer(serializers.Serializer[Any]):
    """The lifecycle command's body: publish, or archive.

    ``draft`` is not accepted here. An article becomes a draft by being created, and an
    archived one is reopened by editing it, so there is no silent unpublish.
    """

    status = serializers.ChoiceField(
        choices=[ArticleStatus.PUBLISHED, ArticleStatus.ARCHIVED],
        required=False,
        default=ArticleStatus.PUBLISHED,
    )


class ArticleListQuerySerializer(serializers.Serializer[Any]):
    """The list screen's filters, validated before they reach the ORM."""

    status = serializers.ChoiceField(
        choices=["all", *ArticleStatus.values],
        required=False,
        default="all",
    )
    search = serializers.CharField(required=False, allow_blank=True, max_length=100)
