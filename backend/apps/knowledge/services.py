"""Article reads and lifecycle commands (T7.1).

Every read starts from the caller's already-authorized workspace, so an id from another tenant
is a ``404`` rather than a hint that it exists. The caller's capability is decided by the view
before it gets here; this module decides only what the workspace may do to its own article.

Two rules are worth stating because they are easy to get wrong:

- **An edit is a new version.** ``version`` increments on any content change, and a published
  article is re-queued for indexing at the same time. Until that job finishes the article is
  published but not retrievable, which the editor shows instead of pretending otherwise.
- **Archiving removes the content from retrieval.** The command queues the job that deletes the
  chunks; the retrieval query also filters on publication status, so a lagging job cannot leak
  an archived policy into a draft.
"""

from __future__ import annotations

from uuid import UUID

from django.db import transaction
from django.db.models import Count, F, Q, QuerySet
from django.utils import timezone

from apps.common.models import TaskStatus
from apps.organizations.services import WorkspaceAccess

from .exceptions import ArticleNotFound, ArticleStateConflict
from .indexing import enqueue_index, mark_pending
from .models import ArticleStatus, KnowledgeArticle


def articles_in(access: WorkspaceAccess) -> QuerySet[KnowledgeArticle]:
    """Every article of the authorized workspace, newest activity first."""
    return KnowledgeArticle.objects.filter(workspace_id=access.workspace.pk)


def get_article(*, access: WorkspaceAccess, article_id: UUID) -> KnowledgeArticle:
    """Load one article, or raise :class:`ArticleNotFound` for an unknown or foreign id."""
    article = articles_in(access).filter(pk=article_id).first()
    if article is None:
        raise ArticleNotFound(f"No knowledge article with id {article_id}.")
    return article


def list_articles(
    *,
    access: WorkspaceAccess,
    status: str | None = None,
    search: str | None = None,
) -> QuerySet[KnowledgeArticle]:
    """The workspace's articles, optionally filtered by lifecycle state and title."""
    queryset = (
        articles_in(access)
        # Explicit because an aggregate clears the model's default ordering, and pagination
        # over an unordered queryset can repeat or drop a row between requests.
        .order_by("-updated_at", "id")
        .annotate(
            # Only the current version counts: a stale chunk is not what retrieval sees.
            chunk_count=Count("chunks", filter=Q(chunks__article_version=F("version")))
        )
    )
    if status:
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(title__icontains=search)
    return queryset


def create_article(
    *, access: WorkspaceAccess, title: str, body: str, author_id: UUID | None
) -> KnowledgeArticle:
    """Create a draft. A new article is never published by the same request."""
    return KnowledgeArticle.objects.create(
        workspace_id=access.workspace.pk,
        title=title,
        body=body,
        author_id=author_id,
        status=ArticleStatus.DRAFT,
    )


def update_article(
    *,
    access: WorkspaceAccess,
    article_id: UUID,
    title: str | None = None,
    body: str | None = None,
) -> KnowledgeArticle:
    """Change an article's text, bumping its version and re-queuing indexing if live.

    A no-op edit returns the article untouched: bumping the version on an unchanged body would
    invalidate the chunks and spend a job for nothing.
    """
    article = get_article(access=access, article_id=article_id)

    fields: dict[str, object] = {}
    if title is not None and title != article.title:
        fields["title"] = title
    if body is not None and body != article.body:
        fields["body"] = body
    if not fields:
        return article

    fields["version"] = article.version + 1
    if article.status == ArticleStatus.PUBLISHED:
        # The stored chunks now describe older text, so the job state has to say so.
        fields["index_status"] = TaskStatus.PENDING
        fields["index_error"] = ""

    with transaction.atomic():
        KnowledgeArticle.objects.filter(pk=article.pk).update(**fields)
        article.refresh_from_db()
        if article.status == ArticleStatus.PUBLISHED:
            enqueue_index(article)
    return article


def set_publication(*, access: WorkspaceAccess, article_id: UUID, status: str) -> KnowledgeArticle:
    """Publish or archive an article, queueing the indexing job either way."""
    article = get_article(access=access, article_id=article_id)
    if status == ArticleStatus.ARCHIVED and article.status == ArticleStatus.ARCHIVED:
        raise ArticleStateConflict("This article is already archived.")
    if status == ArticleStatus.PUBLISHED and article.status == ArticleStatus.ARCHIVED:
        # Reopening is an edit, not a publish: the text someone archived is not what should go
        # live again months later without review.
        raise ArticleStateConflict("An archived article must be edited before it is published.")

    now = timezone.now()
    fields: dict[str, object] = {
        "status": status,
        "index_status": TaskStatus.PENDING,
        "index_error": "",
    }
    if status == ArticleStatus.PUBLISHED:
        fields["published_at"] = article.published_at or now
        fields["archived_at"] = None
    else:
        fields["archived_at"] = now

    with transaction.atomic():
        KnowledgeArticle.objects.filter(pk=article.pk).update(**fields)
        article.refresh_from_db()
        enqueue_index(article)
    return article


def request_reindex(*, access: WorkspaceAccess, article_id: UUID) -> KnowledgeArticle:
    """Re-queue indexing for an article, including after a failure.

    Idempotent: two clicks leave one job because the task claims the row before doing any work,
    and a second message finds it running.
    """
    article = get_article(access=access, article_id=article_id)
    with transaction.atomic():
        mark_pending(article)
        enqueue_index(article)
    return article
