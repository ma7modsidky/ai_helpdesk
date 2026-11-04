"""Indexing: chunks, the search vector, idempotency, and failure reporting (T7.2)."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.postgres.search import SearchQuery

from apps.common.models import TaskStatus
from apps.knowledge.indexing import mark_pending
from apps.knowledge.models import ArticleStatus, KnowledgeChunk
from apps.knowledge.tasks import index_article
from apps.knowledge.tests.factories import ArticleFactory, indexed_article
from apps.organizations.tests.factories import WorkspaceFactory

pytestmark = pytest.mark.django_db


def test_indexing_a_published_article_stores_searchable_chunks() -> None:
    article = ArticleFactory.create(
        workspace=WorkspaceFactory.create(),
        title="Refund policy",
        body="Refunds are reviewed within five business days.",
        status=ArticleStatus.PUBLISHED,
    )

    outcome = index_article(str(article.pk))

    article.refresh_from_db()
    assert outcome == "succeeded"
    assert article.index_status == TaskStatus.SUCCEEDED
    assert article.indexed_version == 1
    assert article.index_attempts == 1
    assert article.indexed_at is not None
    assert article.chunks.count() == 1

    matched = KnowledgeChunk.objects.filter(search_vector=SearchQuery("refund", config="english"))
    assert list(matched.values_list("article_id", flat=True)) == [article.pk]


def test_the_title_is_part_of_what_retrieval_matches() -> None:
    article = ArticleFactory.create(
        workspace=WorkspaceFactory.create(),
        title="Chargeback policy",
        body="Contact the billing team with the transaction id.",
        status=ArticleStatus.PUBLISHED,
    )

    index_article(str(article.pk))

    assert KnowledgeChunk.objects.filter(
        article=article, search_vector=SearchQuery("chargeback", config="english")
    ).exists()


def test_an_arabic_article_is_searchable_with_the_arabic_configuration() -> None:
    article = ArticleFactory.create(
        workspace=WorkspaceFactory.create(),
        title="سياسة استرداد المبالغ المكررة",
        body="يتم رد المبلغ المكرر إلى وسيلة الدفع الأصلية خلال خمسة أيام عمل.",
        status=ArticleStatus.PUBLISHED,
    )

    index_article(str(article.pk))

    assert KnowledgeChunk.objects.filter(
        article=article, search_vector=SearchQuery("المكررة", config="arabic")
    ).exists()


def test_one_vector_carries_the_lexemes_of_every_language() -> None:
    article = ArticleFactory.create(
        workspace=WorkspaceFactory.create(),
        title="Refund and استرداد policy",
        body="Refunds take five days. يتم الرد خلال خمسة أيام.",
        status=ArticleStatus.PUBLISHED,
    )

    index_article(str(article.pk))

    chunk = article.chunks.get()
    assert KnowledgeChunk.objects.filter(
        pk=chunk.pk, search_vector=SearchQuery("refund", config="english")
    ).exists()
    assert KnowledgeChunk.objects.filter(
        pk=chunk.pk, search_vector=SearchQuery("الرد", config="arabic")
    ).exists()


def test_indexing_a_draft_article_stores_nothing() -> None:
    article = indexed_article(workspace=WorkspaceFactory.create())
    assert article.chunks.exists()

    # An article moved back to draft must lose its retrievable content, not keep it.
    article.status = ArticleStatus.DRAFT
    article.save(update_fields=["status"])
    # The service queues a job by resetting the state; a bare model save does not.
    mark_pending(article)
    outcome = index_article(str(article.pk))

    article.refresh_from_db()
    assert outcome == "cleared"
    assert article.index_status == TaskStatus.SUCCEEDED
    assert not article.chunks.exists()


def test_archiving_through_the_task_removes_the_chunks() -> None:
    article = indexed_article(workspace=WorkspaceFactory.create())
    article.status = ArticleStatus.ARCHIVED
    article.save(update_fields=["status"])
    mark_pending(article)

    index_article(str(article.pk))

    assert not KnowledgeChunk.objects.filter(article=article).exists()


def test_a_duplicate_delivery_is_skipped() -> None:
    article = ArticleFactory.create(
        workspace=WorkspaceFactory.create(), status=ArticleStatus.PUBLISHED
    )

    first = index_article(str(article.pk))
    second = index_article(str(article.pk))

    article.refresh_from_db()
    assert (first, second) == ("succeeded", "skipped")
    assert article.index_attempts == 1


def test_a_failure_is_recorded_and_can_be_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    article = ArticleFactory.create(
        workspace=WorkspaceFactory.create(), status=ArticleStatus.PUBLISHED
    )

    def explode(article: Any) -> int:
        raise RuntimeError("the database went away")

    monkeypatch.setattr("apps.knowledge.tasks.replace_chunks", explode)
    with pytest.raises(RuntimeError):
        index_article(str(article.pk))

    article.refresh_from_db()
    assert article.index_status == TaskStatus.FAILED
    # The class, never the message: a message can quote stored content.
    assert article.index_error == "RuntimeError"

    monkeypatch.undo()
    assert index_article(str(article.pk)) == "succeeded"
    article.refresh_from_db()
    assert article.index_status == TaskStatus.SUCCEEDED
    assert article.index_attempts == 2
    assert article.index_error == ""


def test_reindexing_an_edited_article_replaces_the_old_version() -> None:
    article = indexed_article(workspace=WorkspaceFactory.create())
    article.body = "Shipping takes two days.\n\nReturns are free within thirty days."
    article.version = 2
    article.save(update_fields=["body", "version"])
    mark_pending(article)

    index_article(str(article.pk))

    article.refresh_from_db()
    assert article.indexed_version == 2
    assert not KnowledgeChunk.objects.filter(article=article, article_version=1).exists()
    assert KnowledgeChunk.objects.filter(article=article, article_version=2).count() == 1


def test_a_missing_article_is_reported_rather_than_ignored() -> None:
    from apps.knowledge.indexing import ArticleNotFound

    with pytest.raises(ArticleNotFound):
        index_article("00000000-0000-0000-0000-000000000000")
