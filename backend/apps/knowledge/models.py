"""Knowledge articles and their retrievable chunks (T7.1, T7.2).

An article has two independent states and keeping them separate is the point of this module:

- ``status`` is the publication lifecycle a person controls: ``draft``, ``published``,
  ``archived``. Only ``published`` content may reach a model (FR-032).
- ``index_status`` is the background job state: ``pending``, ``running``, ``succeeded``,
  ``failed``. A published article whose indexing failed is live on the screen and absent from
  retrieval, which the editor has to be able to see — that is why the job state is stored on
  the article rather than only in a log line.

``version`` is bumped by every content edit and stamped onto each chunk. Retrieval filters
``chunk.article_version == article.version``, so a chunk written from older text can never be
cited as current no matter which jobs are in flight (05 §4).

The workspace is copied onto a chunk as well as reachable through the article. That redundancy
is deliberate: the tenant filter in retrieval is applied to the chunk table itself, before any
content is assembled into a prompt, so a join cannot be forgotten (10_SECURITY).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from apps.common.models import TaskStatus

TITLE_MAX = 200
BODY_MAX = 20_000
ERROR_CLASS_MAX = 100

# PostgreSQL's built-in text-search configuration. Named in one place because the indexing
# vector and the retrieval query must use the same one, or nothing ever matches.
SEARCH_CONFIG = "english"


class ArticleStatus(models.TextChoices):
    """The publication lifecycle (FR-030, FR-032)."""

    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class KnowledgeArticle(models.Model):
    """One help-centre article, owned by a workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "organizations.Workspace",
        on_delete=models.CASCADE,
        related_name="articles",
    )
    title = models.CharField(max_length=TITLE_MAX)
    body = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=ArticleStatus.choices,
        default=ArticleStatus.DRAFT,
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Bumped by every content edit; chunks are stamped with it.",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_articles",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    index_status = models.CharField(
        max_length=16,
        choices=TaskStatus.choices,
        default=TaskStatus.PENDING,
        help_text="State of the chunk/index job for this article.",
    )
    indexed_version = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="The version the stored chunks were built from, if any.",
    )
    index_attempts = models.PositiveSmallIntegerField(default=0)
    index_error = models.CharField(
        max_length=ERROR_CLASS_MAX,
        blank=True,
        default="",
        help_text="Exception class of the last failed attempt; never its message.",
    )
    indexed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=ArticleStatus.values),
                name="article_status_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(index_status__in=TaskStatus.values),
                name="article_index_status_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="article_version_is_positive",
            ),
        ]
        indexes = [
            # The list screen's default order and its status tabs.
            models.Index(fields=("workspace", "-updated_at"), name="article_ws_updated_idx"),
            models.Index(
                fields=("workspace", "status", "updated_at"),
                name="article_ws_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"

    @property
    def is_retrievable(self) -> bool:
        """Whether the stored chunks of this article may be offered to a model."""
        return (
            self.status == ArticleStatus.PUBLISHED
            and self.indexed_version == self.version
            and self.index_status == TaskStatus.SUCCEEDED
        )


class KnowledgeChunk(models.Model):
    """A bounded piece of one article version, and the vector retrieval searches.

    The unique constraint is on ``(article, article_version, chunk_index)``: a reindex of the
    same version rewrites the same rows, so a retried job converges instead of duplicating
    context. Older versions are deleted when a newer one is indexed; keeping them would let a
    stale answer be cited with a current-looking title.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "organizations.Workspace",
        on_delete=models.CASCADE,
        related_name="knowledge_chunks",
    )
    article = models.ForeignKey(
        KnowledgeArticle,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    article_version = models.PositiveIntegerField()
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    # Nullable rather than defaulted: an empty tsvector literal is a valid value, but a row
    # with no vector is unambiguous and is simply never matched.
    search_vector = SearchVectorField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("article_version", "chunk_index", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("article", "article_version", "chunk_index"),
                name="unique_chunk_per_version",
            ),
            models.CheckConstraint(
                condition=models.Q(article_version__gte=1),
                name="chunk_article_version_is_positive",
            ),
        ]
        indexes = [
            # The retrieval query: one full-text match, ranked.
            GinIndex(fields=["search_vector"], name="knowledge_chunk_search_idx"),
            # Deleting the chunks of one article, and counting them for the editor.
            models.Index(fields=("workspace", "article"), name="chunk_ws_article_idx"),
        ]

    def __str__(self) -> str:
        return f"chunk {self.article_id} v{self.article_version} #{self.chunk_index}"
