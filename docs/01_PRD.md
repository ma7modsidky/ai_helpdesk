# 01 — Product Requirements Document (PRD)

## 1. Product summary

**Working name:** ResolveAI Helpdesk  
**Product type:** Multi-tenant B2B SaaS  
**Primary users:** Small support teams, support managers, and their customers  
**Problem:** Support requests are difficult to prioritize and resolve consistently when they live in scattered inboxes and employees lack shared context. Managers also need visibility into response deadlines and recurring customer problems.

ResolveAI provides a shared ticket workspace with AI-assisted classification, knowledge-grounded reply drafts, SLA tracking, and auditable human-controlled workflows.

## 2. Goals

1. Demonstrate sound full-stack engineering and system design.
2. Reduce repetitive support work using AI assistance, without surrendering human approval.
3. Demonstrate tenant isolation, role-based permissions, reliable background processing, and observability.
4. Be quick to run locally and straightforward to deploy as a portfolio demo.
5. Keep the core application useful even if Redis, RabbitMQ, Celery, or the LLM provider is temporarily unavailable.

## 3. Non-goals for MVP

- Fully autonomous replies sent to customers.
- Email ingestion from arbitrary mailboxes.
- WhatsApp, social media, or telephony integrations.
- Payments, subscription billing, and metered commercial billing.
- Complex visual workflow builder.
- Analytics dashboards, reporting exports, and trend visualisation: `GET .../analytics/overview/` is
  removed from the MVP contract (ADR-025).
- A customer self-service portal: customers are captured as contact details on a ticket, not as users
  (ADR-020, ADR-025).
- Team- or queue-based routing: teams are post-MVP and tickets have no `team_id` (ADR-024).
- Multi-region deployment or Kubernetes.
- Locales beyond English and Arabic: the architecture supports more, MVP ships two.
- Server-side rendering and a native mobile application.
- Formal legal/compliance certification.
- Storing payment-card data or sensitive medical data.

## 4. Personas

### Workspace owner/admin
Creates a workspace, invites members, configures roles, SLA policies, and approved knowledge sources.

### Support manager
Monitors ticket queues, workload, deadlines, escalations, and team performance.

### Support agent
Works assigned tickets, sends messages, adds internal notes, reviews AI drafts, and resolves issues.

### Customer/requester
Submits a ticket and can see only their own tickets and customer-visible replies if a customer portal is included in the MVP.

### Platform operator
Maintains service health and investigates failures; access to customer content must be minimized and audited.

## 5. Core user journeys

### Journey A — Ticket resolution
1. Customer or agent creates a ticket.
2. Backend validates and persists the ticket.
3. Backend records an AI-processing request after successful persistence.
4. Celery worker classifies category/sentiment/suggested priority and drafts a response.
5. Agent opens ticket, reviews the AI suggestion and source articles, edits if needed, and sends a reply.
6. Ticket status and audit trail are updated.
7. SLA and dashboard metrics reflect the event.

### Journey B — Knowledge-grounded assistance
1. Admin adds an approved knowledge article.
2. System chunks and indexes article content.
3. Agent requests a suggested reply or asks a question.
4. Retrieval searches only within the current workspace.
5. LLM receives ticket context and retrieved snippets as untrusted reference material.
6. UI shows draft and cited source articles.
7. Agent verifies and approves the reply.

### Journey C — SLA escalation
1. Workspace admin defines response targets and escalation rules.
2. Ticket receives a deadline based on priority/policy.
3. Periodic task identifies tickets nearing or exceeding deadlines.
4. System records one escalation event per rule/ticket occurrence and queues notifications.
5. Manager sees overdue state and escalation history.

## 6. Functional requirements

### Authentication and workspaces
- FR-001: Users can authenticate using a supported secure authentication flow. A new user can self-register with an email address and password; the account starts with no workspace and gains access only by creating one or accepting an invitation.
- FR-002: A user can belong to multiple workspaces, with a role per membership.
- FR-003: Workspace membership and role are checked on every protected operation.
- FR-004: Workspace creation/invitation is controlled; never allow a client-supplied workspace ID alone to grant access.
- FR-005: Workspace members can invite/remove members according to role policy. An invitation is single-use, expires after a fixed window, can be revoked or resent, grants at most `admin`, and is accepted only by an account with the invited email address.
- FR-006: A workspace owner can transfer ownership to another active member in one atomic operation, and a workspace always retains at least one active owner.

### Tickets and conversations
- FR-010: Authorized users can create and list tickets within their workspace.
- FR-011: Tickets have subject, description, status, priority, category, requester, assignee, timestamps, and SLA timestamps where applicable. The requester is captured as an email (with an optional name) so a customer does not need an account; `requester_user_id` is set only when the requester is also a member (ADR-020).
- FR-012: Agents can assign tickets and change status only through validated transitions.
- FR-013: Messages are classified as customer-visible replies or internal notes.
- FR-014: Customer-visible replies and internal notes are rendered distinctly and are never exposed across roles incorrectly.
- FR-015: Important changes are recorded in an append-only audit event stream.
- FR-016: Ticket lists support pagination, filtering, ordering, and bounded page sizes.

### AI assistant
- FR-020: AI processing is asynchronous by default.
- FR-021: AI classification returns validated structured fields: category, sentiment, suggested priority, and concise rationale.
- FR-022: AI generates reply drafts but never sends them automatically in MVP.
- FR-023: Reply drafts use workspace-scoped approved knowledge snippets where available.
- FR-024: UI displays draft status: pending, processing, ready, failed.
- FR-025: Failed jobs can be retried safely with limits and backoff.
- FR-026: The system stores model/provider metadata, duration, token/usage estimates where available, and outcome, but avoids logging full sensitive prompts by default.
- FR-027: AI output is treated as untrusted; validate schemas, escape rendered text, and do not execute instructions contained in ticket content or retrieved documents.

### Knowledge base
- FR-030: Admins can create, update, archive, and view articles.
- FR-031: Articles have title, body, status, version/timestamps, and workspace ownership.
- FR-032: Only approved/published articles are eligible for retrieval.
- FR-033: Article ingestion/chunking/embedding is asynchronous.
- FR-034: Retrieval always applies workspace scope before ranking or returning content.
- FR-035: AI suggestions include source references; if no reliable sources are found, the UI states that the draft is not grounded in available documentation.

### SLA and automation
- FR-040: Admins can configure first-response targets by priority for MVP.
- FR-041: The system calculates deadlines using one explicitly documented time policy. MVP may use elapsed time rather than business-hours calendars.
- FR-042: A periodic job identifies approaching and breached deadlines.
- FR-043: Escalation/notification events are idempotent and auditable.
- FR-044: Changing priority or policy recalculates the deadline through a domain service.
- FR-045: A ticket that has received a qualifying public response is not repeatedly escalated for the same first-response deadline.

### Interface and localization
- FR-060: The interface is bilingual, English (`en`, left-to-right) and Arabic (`ar`, right-to-left). Every
  user-visible string comes from a translation catalog; no screen is shipped in one language only, and
  switching language applies direction, typography, and formatting together without a reload.
- FR-061: A user can choose light, dark, or system theme, and the choice persists between visits.
- FR-062: Every data screen has explicit loading, empty, error, forbidden, and conflict states, and never
  displays a raw backend error or stack trace.
- FR-063: The application is keyboard operable and meets WCAG 2.2 AA contrast, labelling, and focus
  requirements in both languages and both themes.

### Operations
- FR-050: Health/readiness checks distinguish application health from dependency readiness.
- FR-051: Logs include request/correlation IDs and task IDs where applicable, without secrets or unnecessary ticket contents.
- FR-052: Errors are observable, actionable, and do not expose stack traces to clients.
- FR-053: Demo seed data is fictional and contains no real personal information.
- FR-054: Retention and deletion behavior for tickets, messages, audit events, AI results, and workspaces is documented and enforced by a scheduled management command.

## 7. Non-functional requirements

- Security: tenant isolation, least privilege, secure secrets, safe file/content handling, throttling, auditability.
- Reliability: API ticket creation does not synchronously depend on LLM availability; background tasks retry safely.
- Performance: paginate list endpoints; avoid N+1 queries; index measured filter/sort paths; set explicit LLM/network timeouts.
- Maintainability: type hints, small modules, service/domain boundaries, consistent error format, meaningful tests.
- Accessibility: keyboard-friendly forms, labels, visible focus states, semantic HTML, accessible status feedback, WCAG 2.2 AA contrast in both themes.
- Localization: English and Arabic with correct text direction, locale-aware dates and numbers, and no layout that assumes one direction (FR-060).
- Observability: structured logs, task failure visibility, basic metrics for queue depth, task duration, AI latency/failure rate, SLA breaches.
- Portability: Docker Compose local environment and environment-variable configuration.

## 8. MVP success criteria

- A clean clone can be started by following README instructions.
- A demo user can create a workspace and complete the ticket workflow.
- Tests prove that users from workspace A cannot access workspace B's tickets, messages, knowledge articles, or AI retrieval results.
- A simulated LLM outage does not prevent ticket creation.
- Duplicate task delivery does not create duplicate messages/escalations.
- AI-generated replies remain drafts until an authorized human sends them.
- CI passes on the default branch.
- The interface is usable end to end in Arabic (right-to-left) and English (left-to-right), in light and dark themes, with no untranslated string and no layout that breaks when direction changes.
- A short demo shows ticket creation, AI assistance, reply approval, and SLA escalation.

## 9. Product risks

- LLM output may be inaccurate or unsafe: use grounded drafts, source references, human approval, and evaluation tests.
- API/worker failure can leave jobs pending: use explicit processing states, retries, monitoring, and a recovery/reconciliation task.
- Tenant leakage can be severe: enforce scope in querysets/services and test negative cross-tenant cases.
- Scope creep can delay delivery: maintain a clear MVP/non-goal list.
