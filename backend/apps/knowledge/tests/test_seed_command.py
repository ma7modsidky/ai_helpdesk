"""The seed command produces a corpus retrieval can actually cite.

The point of the command is the end state, not its output: published, indexed articles that a
ticket's own words match. These tests assert that rather than the number of log lines, so the
corpus can be edited without rewriting them.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.tests.factories import UserFactory
from apps.ai_assistant.sources import candidates_for
from apps.common.models import TaskStatus
from apps.knowledge.management.commands.seed_knowledge import SEED_ARTICLES
from apps.knowledge.models import ArticleStatus, KnowledgeArticle
from apps.organizations.models import MembershipRole, Workspace
from apps.organizations.tests.factories import MembershipFactory, WorkspaceFactory
from apps.tickets.tests.factories import TicketFactory

pytestmark = pytest.mark.django_db

SLUG = "acme-support"


def seed(*args: str) -> str:
    """Run the command with its output captured, returning what it wrote."""
    out = StringIO()
    call_command("seed_knowledge", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


def workspace() -> Workspace:
    created = WorkspaceFactory.create(slug=SLUG, name="Acme Support")
    MembershipFactory.create(workspace=created, role=MembershipRole.OWNER)
    return created


def test_seeded_articles_are_published_and_indexed() -> None:
    created = workspace()

    output = seed("--workspace", SLUG)

    articles = KnowledgeArticle.objects.filter(workspace=created)
    assert articles.count() == len(SEED_ARTICLES)
    assert set(articles.values_list("status", flat=True)) == {ArticleStatus.PUBLISHED}
    assert set(articles.values_list("index_status", flat=True)) == {TaskStatus.SUCCEEDED}
    # Chunks are what retrieval reads, so a published article with none would still not help.
    assert all(article.chunks.exists() for article in articles)
    assert f"{len(SEED_ARTICLES)} article(s) published" in output


def test_a_duplicate_charge_ticket_retrieves_the_refund_article() -> None:
    created = workspace()
    seed("--workspace", SLUG)

    ticket = TicketFactory.create(
        workspace=created,
        subject="Duplicate subscription charge",
        description="I was charged twice for the same month on my card.",
    )

    sources = candidates_for(ticket=ticket)

    assert sources, "a duplicate-charge ticket should match the seeded refund article"
    assert any("refund" in source.title.lower() for source in sources)
    # A citation must resolve to an article, not to a chunk of one.
    assert all(source.article_id for source in sources)


def test_an_arabic_ticket_retrieves_the_arabic_article() -> None:
    created = workspace()
    seed("--workspace", SLUG)

    ticket = TicketFactory.create(
        workspace=created,
        subject="خصم مكرر على البطاقة",
        description="تم خصم المبلغ مرتين وأريد استرداد المبلغ المكرر.",
    )

    sources = candidates_for(ticket=ticket)

    assert any("المكررة" in source.title for source in sources)


def test_the_corpus_stays_inside_its_own_workspace() -> None:
    workspace()
    seed("--workspace", SLUG)
    other = WorkspaceFactory.create(slug="other-tenant", name="Other")
    ticket = TicketFactory.create(
        workspace=other,
        subject="Duplicate subscription charge",
        description="I was charged twice for the same month on my card.",
    )

    assert candidates_for(ticket=ticket) == []


def test_running_twice_adds_nothing() -> None:
    created = workspace()
    seed("--workspace", SLUG)

    output = seed("--workspace", SLUG)

    assert KnowledgeArticle.objects.filter(workspace=created).count() == len(SEED_ARTICLES)
    assert f"0 article(s) published and indexed, {len(SEED_ARTICLES)} already present" in output


def test_an_unknown_workspace_is_refused_with_the_active_ones() -> None:
    workspace()

    with pytest.raises(CommandError, match=SLUG):
        seed("--workspace", "missing-slug")


def test_an_author_from_outside_the_workspace_is_refused() -> None:
    workspace()
    stranger = UserFactory.create()

    with pytest.raises(CommandError, match="not an active member"):
        seed("--workspace", SLUG, "--author", stranger.email)


def test_the_author_is_recorded_on_every_article() -> None:
    created = workspace()
    member = MembershipFactory.create(workspace=created, role=MembershipRole.AGENT).user

    seed("--workspace", SLUG, "--author", member.email)

    authors = KnowledgeArticle.objects.filter(workspace=created).values_list("author_id", flat=True)
    assert set(authors) == {member.pk}
