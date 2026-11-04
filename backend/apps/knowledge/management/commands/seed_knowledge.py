"""Publish a small help-centre corpus so a draft has something to cite (T7.6, FR-032).

Retrieval only offers published, currently indexed articles (ADR-038), so a fresh workspace can
never produce a grounded draft: the prompt is told there are no sources, and the panel says the
draft rests on nothing. This command seeds a handful of realistic articles into an existing
workspace and indexes them before it returns, so a demo shows citations instead of the
ungrounded fallback.

Two properties worth stating:

- **Idempotent by title.** Running it twice adds nothing, which is what lets it sit in a demo
  checklist without needing a reset step or a fresh database.
- **Indexing runs inline as well as through the queue.** The queued message is published by the
  service (so a worker indexes it in the normal way), and the task is then called directly here
  because the point of a seed is that retrieval works the moment the command exits. The claim
  convention makes the second run a no-op rather than duplicate work.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import User
from apps.common.models import TaskStatus
from apps.knowledge.models import ArticleStatus, KnowledgeArticle
from apps.knowledge.services import create_article, set_publication
from apps.knowledge.tasks import index_article
from apps.organizations.exceptions import WorkspaceNotFound
from apps.organizations.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Workspace,
    WorkspaceStatus,
)
from apps.organizations.services import resolve_workspace_access

# Written as support content a customer would actually be answered with: two short paragraphs
# each, with the words a ticket uses (duplicate charge, reset link, tracking, outage, escalation)
# in the body as well as the title, because retrieval matches both. One article is in Arabic: the
# interface is bilingual, so a demo needs a source an Arabic ticket can cite (ADR-039).
SEED_ARTICLES: tuple[tuple[str, str], ...] = (
    (
        "Refund policy for duplicate charges",
        "Duplicate charges are refunded in full to the original payment method. Confirm that both "
        "transactions share the same amount and billing date before treating the second one as a "
        "duplicate, because a partially refunded order can look like a second charge.\n\n"
        "Approved refunds are issued within five business days and normally appear on the "
        "customer's statement within ten business days. Ask for the transaction id from the bank "
        "statement rather than a screenshot, and quote that id when you confirm the refund.",
    ),
    (
        "سياسة استرداد المبالغ المكررة",
        "يتم رد المبلغ المكرر بالكامل إلى وسيلة الدفع الأصلية بعد التأكد من أن العمليتين تحملان "
        "المبلغ والتاريخ نفسه، لأن الطلب المسترد جزئياً قد يبدو كخصم ثانٍ.\n\n"
        "تُصرف المبالغ المستردة خلال خمسة أيام عمل، وتظهر عادةً في كشف الحساب خلال عشرة أيام "
        "عمل. اطلب رقم العملية من كشف الحساب البنكي واذكره عند تأكيد الاسترداد.",
    ),
    (
        "Changing or cancelling a subscription",
        "Customers can cancel at any time from billing settings. Cancellation stops the next "
        "renewal: access continues until the end of the paid billing period, and no partial refund "
        "is issued for the remaining days.\n\n"
        "A downgrade from an annual plan to a monthly plan takes effect at renewal. Upgrades are "
        "charged immediately and prorated against the unused remainder of the current plan. "
        "Invoices for the new plan appear under billing history; a past invoice is never "
        "rewritten.",
    ),
    (
        "Resetting a password and recovering access",
        "A password reset link is valid for thirty minutes and can be used once. Ask the customer "
        "to request a new link if theirs expired rather than sending one yourself, and never ask "
        "for a password in a reply.\n\n"
        "Five failed sign-in attempts lock the account for fifteen minutes. Accounts that sign in "
        "through SSO cannot reset a password here, because the identity provider owns the "
        "credentials; send them to their administrator. If the invited email address no longer "
        "works, a workspace admin has to invite the new address.",
    ),
    (
        "Delivery times and tracking an order",
        "Orders ship within two business days of payment clearing, and the tracking number is "
        "emailed as soon as the carrier scans the parcel. Tracking pages can lag behind the parcel "
        "by up to a day.\n\n"
        "A parcel that has not moved for five business days counts as delayed: open a trace with "
        "the carrier and give the customer the reference number. A parcel still missing after ten "
        "business days is replaced at no cost. Address changes are only possible before the "
        "carrier scan.",
    ),
    (
        "Service outages and incident updates",
        "During an outage the status page carries the incident, the affected components, and the "
        "time of the next update. Support replies should quote the incident id, acknowledge the "
        "impact, and avoid promising a fix time the incident has not stated.\n\n"
        "A post-incident summary is published within three business days. Downtime credits are "
        "issued automatically to affected accounts on the next invoice, so a customer who asks for "
        "a credit does not need to file anything separately.",
    ),
    (
        "Response times and escalation",
        "First-response targets are one hour for urgent tickets, four business hours for high "
        "priority, and one business day for normal priority. The clock starts when the ticket is "
        "created and pauses while the ticket waits on the customer.\n\n"
        "A ticket that breaches its target is escalated to the workspace manager. The escalation "
        "is recorded on the ticket so the customer sees one consistent thread, while internal "
        "notes about the escalation stay internal.",
    ),
)


class Command(BaseCommand):
    help = (
        "Publish a few realistic help-centre articles into a workspace and index them, so an AI "
        "draft has sources to cite. Safe to run more than once."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--workspace",
            required=True,
            help="Slug of the workspace to seed. An unknown slug lists the active ones.",
        )
        parser.add_argument(
            "--author",
            default=None,
            help="Email of the member recorded as author (default: the workspace owner).",
        )

    def handle(self, *args: Any, **options: Any) -> str | None:
        slug = str(options["workspace"])
        workspace = Workspace.objects.filter(slug=slug, status=WorkspaceStatus.ACTIVE).first()
        if workspace is None:
            raise CommandError(
                f"No active workspace with slug {slug!r}. "
                f"Active workspaces: {self._active_slugs()}."
            )

        author = self._author(workspace, options["author"])
        try:
            access = resolve_workspace_access(user=author, workspace_id=workspace.pk)
        except WorkspaceNotFound as exc:
            raise CommandError(
                f"{author.email} is not an active member of {workspace.slug}."
            ) from exc

        published = 0
        skipped = 0
        for title, body in SEED_ARTICLES:
            if KnowledgeArticle.objects.filter(workspace=workspace, title=title).exists():
                skipped += 1
                self.stdout.write(f"already present  {title}")
                continue

            article = create_article(access=access, title=title, body=body, author_id=author.pk)
            set_publication(access=access, article_id=article.pk, status=ArticleStatus.PUBLISHED)
            # The service queued the job; running it here too means retrieval is ready on exit.
            index_article(str(article.pk))
            article.refresh_from_db()
            published += 1

            chunks = article.chunks.filter(article_version=article.version).count()
            if article.index_status == TaskStatus.SUCCEEDED:
                self.stdout.write(
                    self.style.SUCCESS(f"published        {title} ({chunks} chunk(s))")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"published        {title}, indexing is {article.index_status}: start the "
                        "worker or use Reindex on the article before relying on it."
                    )
                )

        self.stdout.write(
            f"{published} article(s) published and indexed, {skipped} already present, "
            f"in workspace {workspace.slug}."
        )
        return None

    def _active_slugs(self) -> str:
        """The ten active slugs, so a typo is answered instead of only refused."""
        slugs = list(
            Workspace.objects.filter(status=WorkspaceStatus.ACTIVE)
            .order_by("slug")
            .values_list("slug", flat=True)[:10]
        )
        return ", ".join(slugs) if slugs else "none"

    def _author(self, workspace: Workspace, email: str | None) -> User:
        """The account recorded as author, defaulting to the workspace's owner."""
        if email:
            user = User.objects.filter(email=email.lower(), is_active=True).first()
            if user is None:
                raise CommandError(f"No active account with email {email!r}.")
            return user

        membership = (
            Membership.objects.select_related("user")
            .filter(
                workspace=workspace,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
            .first()
        )
        if membership is None:
            raise CommandError(f"{workspace.slug} has no active owner; pass --author.")
        return membership.user
