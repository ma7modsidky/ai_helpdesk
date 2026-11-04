"""Factories for knowledge-base tests.

The default article is a published, indexed one whose body is a single paragraph about
refunds: retrieval tests need something a ticket can actually match, and a test that cares
about the lifecycle asks for a draft or an archived article explicitly.
"""

from __future__ import annotations

import factory
from factory.declarations import Sequence, SubFactory

from apps.knowledge.models import ArticleStatus, KnowledgeArticle
from apps.knowledge.tasks import index_article
from apps.organizations.models import Workspace
from apps.organizations.tests.factories import WorkspaceFactory

DEFAULT_BODY = (
    "Refunds are reviewed within five business days. A duplicate charge is refunded to the "
    "original payment method once the transaction is confirmed."
)


class ArticleFactory(factory.django.DjangoModelFactory[KnowledgeArticle]):
    class Meta:
        model = KnowledgeArticle

    workspace = SubFactory(WorkspaceFactory)  # type: ignore[no-untyped-call]
    title = Sequence(lambda index: f"Article {index}")  # type: ignore[no-untyped-call]
    body = DEFAULT_BODY
    status = ArticleStatus.PUBLISHED


def indexed_article(
    *,
    workspace: Workspace,
    title: str = "Refund policy",
    body: str = DEFAULT_BODY,
    status: str = ArticleStatus.PUBLISHED,
) -> KnowledgeArticle:
    """Create an article and run its indexing job synchronously.

    Called directly rather than through the queue: the point of these tests is what indexing
    produces, and waiting for a `transaction.on_commit` callback would only add ceremony.
    """
    article = ArticleFactory.create(workspace=workspace, title=title, body=body, status=status)
    index_article(str(article.pk))
    article.refresh_from_db()
    return article
