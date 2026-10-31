"""Report background-task state from the database (T5.4).

Deliberately broker-free: an operator asking \"is work moving?\" should get an answer even when
the queue or the workers are the thing that is broken. Readiness of the API stays tied to
PostgreSQL (D-14); this command and the structured task logs carry the operational signal
instead of taking the API out of rotation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.common.task_records import TaskSummary, summary


class Command(BaseCommand):
    help = "Print task counts by status and list work that stopped progressing."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--stale-minutes",
            type=int,
            default=15,
            help="A running record older than this is considered stuck (default: 15).",
        )
        parser.add_argument(
            "--fail-on-stuck",
            action="store_true",
            help="Exit non-zero when stuck work exists, for use in a monitoring loop.",
        )

    def handle(self, *args: Any, **options: Any) -> str | None:
        stale_minutes = int(options["stale_minutes"])
        if stale_minutes < 1:
            raise CommandError("--stale-minutes must be positive.")

        report: TaskSummary = summary(stale_after=timedelta(minutes=stale_minutes))

        for status, count in report.counts.items():
            self.stdout.write(f"{status}: {count}")

        if report.oldest_pending_seconds is None:
            self.stdout.write("oldest pending: none")
        else:
            self.stdout.write(f"oldest pending: {report.oldest_pending_seconds:.0f}s")

        if report.stuck:
            self.stdout.write(
                self.style.WARNING(
                    f"stuck running (>{stale_minutes}m): {len(report.stuck)} "
                    "— the worker may have died mid-task."
                )
            )
            for record in report.stuck:
                self.stdout.write(
                    f"  {record.task_name} {record.id} started {record.started_at}:"
                    f"{record.attempts} attempt(s)"
                )
            if options["fail_on_stuck"]:
                raise CommandError("Stuck background work found.")
        else:
            self.stdout.write("stuck running: 0")

        return None
