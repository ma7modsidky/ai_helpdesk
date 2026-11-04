"""Article indexing: claiming a job, rewriting chunks, and recording the outcome (T7.2).

The claim convention is the same one the AI jobs use (ADR-033): a worker takes the article only
from ``pending`` or ``failed``, so a message Celery delivers twice is dropped instead of
re-embedding the same text, and a manual retry is allowed. ``succeeded`` is final.

Replacing chunks is transactional and version-stamped. Deleting the older versions inside the
same transaction means retrieval can never see a mixture of two texts: either the old version
is gone or the new one is complete.
"""

from __future__ import annotations

from uuid import UUID

from django.contrib.postgres.search import SearchVector
from django.db import transaction
from django.db.models import F, Value
from django.utils import timezone

from apps.common.models import TaskStatus
from apps.common.tasking import enqueue

from .chunking import split_body
from .models import (
    ERROR_CLASS_MAX,
    SEARCH_CONFIG,
    ArticleStatus,
    KnowledgeArticle,
    KnowledgeChunk,
)

# How many chunks a reindex rewrites per bulk insert. Small enough to keep the statement
# bounded, large enough that a normal article is one round trip.
_BULK_SIZE = 100


class ArticleNotFound(LookupError):
    """A task ran with an id that no row holds."""


def enqueue_index(article: KnowledgeArticle) -> None:
    """Queue indexing after the transaction that made it necessary commits.

    Imported inside the function because ``tasks`` imports this module for its claim helpers.
    """
    from .tasks import index_article

    enqueue(index_article, str(article.pk))


def mark_pending(article: KnowledgeArticle) -> None:
    """Reset the job state for a new run, so the editor shows queued rather than stale."""
    KnowledgeArticle.objects.filter(pk=article.pk).update(
        index_status=TaskStatus.PENDING,
        index_error="",
    )
    article.refresh_from_db()


def claim(article_id: str | UUID) -> KnowledgeArticle | None:
    """Load and claim an article for indexing, or ``None`` when it must not run."""
    article = KnowledgeArticle.objects.filter(pk=article_id).first()
    if article is None:
        raise ArticleNotFound(f"No knowledge article with id {article_id}.")

    claimed = KnowledgeArticle.objects.filter(
        pk=article.pk,
        index_status__in=(TaskStatus.PENDING, TaskStatus.FAILED),
    ).update(
        index_status=TaskStatus.RUNNING,
        index_attempts=F("index_attempts") + 1,
        index_error="",
        indexed_at=None,
    )
    if not claimed:
        return None

    article.refresh_from_db()
    return article


def replace_chunks(article: KnowledgeArticle) -> int:
    """Rewrite this article's chunks at its current version and return how many exist."""
    chunks = split_body(article.body)
    with transaction.atomic():
        # Two deletes rather than one: the second is what makes a retried job idempotent, and
        # the first is what stops a stale version from being retrievable in between.
        KnowledgeChunk.objects.filter(article=article).exclude(
            article_version=article.version
        ).delete()
        KnowledgeChunk.objects.filter(article=article, article_version=article.version).delete()

        rows = [
            KnowledgeChunk(
                workspace_id=article.workspace_id,
                article=article,
                article_version=article.version,
                chunk_index=chunk.index,
                content=chunk.content,
            )
            for chunk in chunks
        ]
        created = KnowledgeChunk.objects.bulk_create(rows, batch_size=_BULK_SIZE)

        # The vector is set per row because it depends on the title as well as the body: a
        # short article whose title says "refund policy" must match a ticket that asks about
        # refunds, even if the body never repeats the word.
        for chunk in created:
            KnowledgeChunk.objects.filter(pk=chunk.pk).update(
                search_vector=SearchVector(
                    Value(article.title),
                    Value(" "),
                    "content",
                    config=SEARCH_CONFIG,
                )
            )
    return len(chunks)


def clear_chunks(article: KnowledgeArticle) -> None:
    """Remove every chunk of an article that is no longer published.

    Nothing archived stays retrievable: the retrieval query already filters on the article
    status, and deleting the rows means an operator who later relaxes that filter still cannot
    resurrect an archived policy.
    """
    KnowledgeChunk.objects.filter(article=article).delete()


def succeed(article: KnowledgeArticle, *, chunks: int) -> None:
    """Record a finished job, including how many chunks it stored."""
    KnowledgeArticle.objects.filter(pk=article.pk).update(
        index_status=TaskStatus.SUCCEEDED,
        index_error="",
        indexed_version=article.version,
        indexed_at=timezone.now(),
    )
    article.refresh_from_db()


def fail(article: KnowledgeArticle, error: BaseException) -> None:
    """Record the failed attempt by exception class only."""
    KnowledgeArticle.objects.filter(pk=article.pk).update(
        index_status=TaskStatus.FAILED,
        index_error=type(error).__name__[:ERROR_CLASS_MAX],
        indexed_at=timezone.now(),
    )
    article.refresh_from_db()


def is_published(article: KnowledgeArticle) -> bool:
    """Whether the article's content may feed retrieval right now."""
    return article.status == ArticleStatus.PUBLISHED
