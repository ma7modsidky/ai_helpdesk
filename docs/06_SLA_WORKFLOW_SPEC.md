# 06 — SLA, Workflow, and Escalation Specification

## MVP policy

Use elapsed-time deadlines initially. Business-hours calendars, holidays, pause/resume accounting, and per-customer contracts are future enhancements. Document this simplification in the UI and README.

## First response SLA

- Select active SLA policy by workspace and ticket priority.
- `first_response_due_at = created_at + first_response_minutes`.
- A qualifying public agent response sets `first_responded_at` once.
- Internal notes do not count as a response.
- A customer reply does not count as the agent's first response.
- If priority changes before first response, recalculate through the SLA service and audit the change.
- Define whether changing policy affects existing tickets; MVP recommendation: new policy applies to new tickets, while existing tickets retain a policy snapshot unless explicitly recalculated.

## Escalation examples

- Approaching deadline: notify assignee when remaining time is under configured threshold.
- Breached deadline: notify manager and mark ticket overdue.
- Unassigned too long: notify manager or assign to a default team.
- Repeated escalation: dedupe by ticket + rule + deadline occurrence.

## Celery tasks

- `process_ticket_ai(ticket_id, job_id)`
- `index_knowledge_article(article_id, version)`
- `check_sla_deadlines()`
- `send_notification(notification_id)`
- `reconcile_stuck_ai_jobs()`

Tasks must load data through services, verify current state at execution time, and be safe under duplicate delivery.

## Idempotency and concurrency

- Use a database unique constraint for escalation event keys.
- Use `transaction.atomic()` for state transitions and event creation.
- Use row locks where concurrent state changes would violate an invariant; avoid broad locks.
- Task execution should re-check that the ticket still qualifies before sending an escalation.
- Notification delivery should record attempts and deduplicate provider callbacks where applicable.
- Use `transaction.on_commit()` or an outbox pattern so tasks do not observe uncommitted rows.

## Acceptance criteria

- Internal notes never satisfy first-response SLA.
- A public reply satisfies the first-response SLA only once.
- Re-running the deadline task creates no duplicate escalation.
- A resolved/responded ticket is not escalated for a condition it no longer meets.
- Provider/email failure can be retried without duplicating the underlying escalation event.
- Deadline calculations are tested at exact boundaries and timezone conversion points.
