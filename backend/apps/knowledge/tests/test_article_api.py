"""The article endpoints and the publication lifecycle (T7.1).

The suite runs with CSRF enforced, so a mutation test proves the same thing a browser does.
Access is the interesting half: reading is a member action, writing is administrative, and a
foreign article is indistinguishable from a missing one.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.common.models import TaskStatus
from apps.knowledge.models import ArticleStatus, KnowledgeArticle, KnowledgeChunk
from apps.knowledge.tests.factories import ArticleFactory, indexed_article
from apps.organizations.models import MembershipRole
from apps.organizations.tests.factories import MembershipFactory, WorkspaceFactory
from tests.support import CsrfClient, login

pytestmark = pytest.mark.django_db

API = "/api/v1"


def articles_url(workspace_id: UUID) -> str:
    return f"{API}/workspaces/{workspace_id}/articles/"


def article_url(workspace_id: UUID, article_id: UUID) -> str:
    return f"{articles_url(workspace_id)}{article_id}/"


def publish_url(workspace_id: UUID, article_id: UUID) -> str:
    return f"{article_url(workspace_id, article_id)}publish/"


def reindex_url(workspace_id: UUID, article_id: UUID) -> str:
    return f"{article_url(workspace_id, article_id)}reindex/"


@pytest.fixture
def workspace() -> Any:
    return WorkspaceFactory.create()


@pytest.fixture
def owner(workspace: Any) -> Any:
    user = UserFactory.create(email="owner@example.com")
    MembershipFactory.create(workspace=workspace, user=user, role=MembershipRole.OWNER)
    return user


@pytest.fixture
def agent(workspace: Any) -> Any:
    user = UserFactory.create(email="agent@example.com")
    MembershipFactory.create(workspace=workspace, user=user, role=MembershipRole.AGENT)
    return user


def sign_in(client: CsrfClient, user: Any) -> CsrfClient:
    return login(client, email=user.email, password=DEFAULT_PASSWORD)


def test_listing_requires_authentication(client: Any) -> None:
    workspace = WorkspaceFactory.create()

    assert client.get(articles_url(workspace.pk)).status_code == 401


def test_a_non_member_cannot_read_articles(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    sign_in(csrf_client, UserFactory.create(email="stranger@example.com"))

    response = csrf_client.get(articles_url(workspace.pk))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_an_agent_reads_the_knowledge_base_but_cannot_write(
    csrf_client: CsrfClient, workspace: Any, agent: Any
) -> None:
    ArticleFactory.create(workspace=workspace)
    sign_in(csrf_client, agent)

    listing = csrf_client.get(articles_url(workspace.pk))
    creation = csrf_client.post_json(articles_url(workspace.pk), {"title": "A", "body": "B"})

    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert creation.status_code == 403
    assert creation.json()["error"]["code"] == "permission_denied"


def test_an_owner_creates_a_draft_and_nothing_is_retrievable_yet(
    csrf_client: CsrfClient, workspace: Any, owner: Any
) -> None:
    sign_in(csrf_client, owner)

    response = csrf_client.post_json(
        articles_url(workspace.pk),
        {"title": "Refund policy", "body": "Refunds take five business days."},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == ArticleStatus.DRAFT
    assert body["version"] == 1
    assert body["author_id"] == str(owner.pk)
    assert body["chunk_count"] == 0
    assert body["published_at"] is None
    # A draft is pending indexing with nothing stored, which is honest rather than "succeeded".
    assert body["indexed_version"] is None
    assert not KnowledgeChunk.objects.exists()


def test_creation_validates_the_title_and_body(
    csrf_client: CsrfClient, workspace: Any, owner: Any
) -> None:
    sign_in(csrf_client, owner)

    empty = csrf_client.post_json(articles_url(workspace.pk), {"title": "", "body": "Body"})
    long_body = csrf_client.post_json(
        articles_url(workspace.pk), {"title": "T", "body": "x" * 20_001}
    )

    assert empty.status_code == 400
    assert "title" in empty.json()["error"]["details"]
    assert long_body.status_code == 400
    assert "body" in long_body.json()["error"]["details"]


def test_an_article_from_another_workspace_is_not_found(
    csrf_client: CsrfClient, workspace: Any, owner: Any
) -> None:
    foreign = ArticleFactory.create()
    sign_in(csrf_client, owner)

    response = csrf_client.get(article_url(workspace.pk, foreign.pk))

    assert response.status_code == 404


def test_publishing_indexes_the_article_and_makes_it_retrievable(
    csrf_client: CsrfClient,
    workspace: Any,
    owner: Any,
    django_capture_on_commit_callbacks: Any,
) -> None:
    draft = ArticleFactory.create(
        workspace=workspace,
        title="Refund policy",
        body="Refunds are reviewed within five business days.",
        status=ArticleStatus.DRAFT,
    )
    sign_in(csrf_client, owner)

    with django_capture_on_commit_callbacks(execute=True):
        response = csrf_client.post_json(
            publish_url(workspace.pk, draft.pk), {"status": ArticleStatus.PUBLISHED}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ArticleStatus.PUBLISHED
    assert body["published_at"] is not None
    # The job is queued after the transaction commits, so the response is honest about being
    # pending; the next read is where a finished job appears.
    assert body["index_status"] == TaskStatus.PENDING

    indexed = csrf_client.get(article_url(workspace.pk, draft.pk)).json()
    assert indexed["index_status"] == TaskStatus.SUCCEEDED
    assert indexed["indexed_version"] == 1
    assert indexed["chunk_count"] == 1
    assert KnowledgeChunk.objects.filter(article=draft).count() == 1


def test_archiving_removes_the_article_from_retrieval(
    csrf_client: CsrfClient,
    workspace: Any,
    owner: Any,
    django_capture_on_commit_callbacks: Any,
) -> None:
    article = indexed_article(workspace=workspace)
    assert KnowledgeChunk.objects.filter(article=article).exists()
    sign_in(csrf_client, owner)

    with django_capture_on_commit_callbacks(execute=True):
        response = csrf_client.post_json(
            publish_url(workspace.pk, article.pk), {"status": ArticleStatus.ARCHIVED}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ArticleStatus.ARCHIVED
    assert body["archived_at"] is not None

    archived = csrf_client.get(article_url(workspace.pk, article.pk)).json()
    assert archived["chunk_count"] == 0
    assert not KnowledgeChunk.objects.filter(article=article).exists()


def test_archiving_twice_is_a_conflict(csrf_client: CsrfClient, workspace: Any, owner: Any) -> None:
    article = ArticleFactory.create(workspace=workspace, status=ArticleStatus.ARCHIVED)
    sign_in(csrf_client, owner)

    response = csrf_client.post_json(
        publish_url(workspace.pk, article.pk), {"status": ArticleStatus.ARCHIVED}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_an_archived_article_must_be_edited_before_it_is_published_again(
    csrf_client: CsrfClient, workspace: Any, owner: Any
) -> None:
    article = ArticleFactory.create(workspace=workspace, status=ArticleStatus.ARCHIVED)
    sign_in(csrf_client, owner)

    response = csrf_client.post_json(
        publish_url(workspace.pk, article.pk), {"status": ArticleStatus.PUBLISHED}
    )

    assert response.status_code == 409


def test_an_unknown_lifecycle_value_is_rejected(
    csrf_client: CsrfClient, workspace: Any, owner: Any
) -> None:
    article = ArticleFactory.create(workspace=workspace, status=ArticleStatus.DRAFT)
    sign_in(csrf_client, owner)

    response = csrf_client.post_json(
        publish_url(workspace.pk, article.pk), {"status": ArticleStatus.DRAFT}
    )

    assert response.status_code == 400


def test_editing_a_published_article_bumps_its_version_and_reindexes(
    csrf_client: CsrfClient,
    workspace: Any,
    owner: Any,
    django_capture_on_commit_callbacks: Any,
) -> None:
    article = indexed_article(workspace=workspace)
    sign_in(csrf_client, owner)

    with django_capture_on_commit_callbacks(execute=True):
        response = csrf_client.patch_json(
            article_url(workspace.pk, article.pk),
            {"body": "Refunds are reviewed within ten business days."},
        )

    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["index_status"] == TaskStatus.PENDING

    edited = csrf_client.get(article_url(workspace.pk, article.pk)).json()
    assert edited["indexed_version"] == 2
    assert edited["index_status"] == TaskStatus.SUCCEEDED
    # The old version's chunks are gone, so nothing can cite the previous text.
    assert not KnowledgeChunk.objects.filter(article=article, article_version=1).exists()


def test_an_edit_with_no_changes_does_not_bump_the_version(
    csrf_client: CsrfClient, workspace: Any, owner: Any
) -> None:
    article = indexed_article(workspace=workspace, title="Refund policy")
    sign_in(csrf_client, owner)

    response = csrf_client.patch_json(
        article_url(workspace.pk, article.pk), {"title": "Refund policy"}
    )

    assert response.status_code == 200
    assert response.json()["version"] == 1


def test_an_empty_edit_is_rejected(csrf_client: CsrfClient, workspace: Any, owner: Any) -> None:
    article = ArticleFactory.create(workspace=workspace)
    sign_in(csrf_client, owner)

    response = csrf_client.patch_json(article_url(workspace.pk, article.pk), {})

    assert response.status_code == 400


def test_reindexing_requeues_the_job(
    csrf_client: CsrfClient,
    workspace: Any,
    owner: Any,
    django_capture_on_commit_callbacks: Any,
) -> None:
    article = indexed_article(workspace=workspace)
    sign_in(csrf_client, owner)

    with django_capture_on_commit_callbacks(execute=True):
        response = csrf_client.post_json(reindex_url(workspace.pk, article.pk), {})

    assert response.status_code == 202
    assert response.json()["index_status"] == TaskStatus.PENDING

    reindexed = csrf_client.get(article_url(workspace.pk, article.pk)).json()
    assert reindexed["index_status"] == TaskStatus.SUCCEEDED
    assert reindexed["indexed_version"] == article.version
    assert reindexed["chunk_count"] == 1


def test_the_list_filters_by_status_and_title(
    csrf_client: CsrfClient, workspace: Any, owner: Any
) -> None:
    ArticleFactory.create(workspace=workspace, title="Refund policy")
    ArticleFactory.create(workspace=workspace, title="Shipping times", status=ArticleStatus.DRAFT)
    sign_in(csrf_client, owner)

    published = csrf_client.get(articles_url(workspace.pk), {"status": "published"})
    searched = csrf_client.get(articles_url(workspace.pk), {"search": "ship"})
    unknown = csrf_client.get(articles_url(workspace.pk), {"status": "deleted"})

    assert [row["title"] for row in published.json()["results"]] == ["Refund policy"]
    assert [row["title"] for row in searched.json()["results"]] == ["Shipping times"]
    assert unknown.status_code == 400


def test_an_archived_article_is_visible_to_readers_but_not_retrievable(
    csrf_client: CsrfClient, workspace: Any, owner: Any
) -> None:
    article = ArticleFactory.create(
        workspace=workspace, status=ArticleStatus.ARCHIVED, title="Old policy"
    )
    sign_in(csrf_client, owner)

    response = csrf_client.get(article_url(workspace.pk, article.pk))

    assert response.status_code == 200
    assert response.json()["status"] == ArticleStatus.ARCHIVED
    assert response.json()["chunk_count"] == 0
    assert not article.chunks.exists()


def test_the_article_body_is_returned_verbatim(
    csrf_client: CsrfClient, workspace: Any, owner: Any
) -> None:
    body = "Line one\n\nLine two with <angle> brackets & symbols"
    article = ArticleFactory.create(workspace=workspace, body=body)
    sign_in(csrf_client, owner)

    response = csrf_client.get(article_url(workspace.pk, article.pk))

    assert response.json()["body"] == body


def test_an_article_is_only_visible_in_its_own_workspace_list(
    csrf_client: CsrfClient, workspace: Any, owner: Any
) -> None:
    ArticleFactory.create(workspace=WorkspaceFactory.create(), title="Someone else's policy")
    ArticleFactory.create(workspace=workspace, title="Our policy")
    sign_in(csrf_client, owner)

    response = csrf_client.get(articles_url(workspace.pk))

    assert [row["title"] for row in response.json()["results"]] == ["Our policy"]
    assert KnowledgeArticle.objects.count() == 2
