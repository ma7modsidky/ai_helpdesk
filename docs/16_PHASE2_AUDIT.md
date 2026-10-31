# 16 — Phase 2 Audit, Traceability, and Open Decisions

**Baseline** `b80047b` (2026-10-27), backend CI green; rows below were updated after T2.5–T2.7 and
T3.1–T3.5 landed (513 tests, 98.19% branch coverage against a 90% floor). No frontend exists yet, so
every frontend row below is a plan claim rather than a code claim.

This document answers one question: **does the implemented system, the API contract, the domain
model, and the task plan agree?** It is a dated snapshot, not a second plan. `08_IMPLEMENTATION_PLAN.md`
stays authoritative for ordering and `15_AGENT_TASK_BACKLOG.md` for task prompts; this file records
where those two disagree with the specs and with the code, and what must be decided before Phase 3.

Re-run this audit at every phase boundary. Update the status columns as work lands; do not inflate
the plan here.

## 1. How the audit was done

Cross-referenced in both directions:

- `04_API_CONTRACT.md` endpoints → plan task → backlog entry → code.
- `03_DOMAIN_AND_DATA_MODEL.md` entities → plan task → migration.
- `01_PRD.md` functional requirements → owning task.
- `10_SECURITY.md`, `11_TEST_STRATEGY.md`, `12_CI_CD.md` requirements → owning task → CI job.
- Phase exit criteria → the tests that prove them.

Three failure classes are distinguished, because they need different responses:

| Class | Meaning | Response |
|---|---|---|
| **Unplanned** | A requirement exists in a spec but no phase or task owns it | Fix the spec set first, then add the task |
| **Unspecified** | A URL or entity is named but has no shape (fields, payload, errors, invariants) | Fill in the spec before implementing |
| **Pending** | Planned for a later phase, correctly absent from the code | Nothing; listed only to show coverage |

A task that is merely "not written yet" for a future phase is **not** a finding. The backlog is
built one phase ahead by design.

## 2. Phase status

| Phase | Exit criterion | Status |
|---|---|---|
| 0 — Repository and decisions | Clean clone starts dependencies; CI runs | **Met with a recorded deviation** — Compose provides PostgreSQL, Redis, RabbitMQ only (`compose.yaml`); backend, frontend, worker, beat, `Dockerfile` and `infra/` from T0.2 do not exist. Datastores start, CI runs, `runserver` works |
| 1 — Backend foundation | Migrations work; tests and checks pass in CI | Met |
| 2 — Tenancy and access control | Tenant isolation proven by tests before ticket features, and a workspace populated and handed over through the API | Met — isolation is proven for both tenant-owned models (`Workspace`, `Membership`) including 404-not-403 refusals, archived workspaces, removed members, and deactivated accounts; registration (T2.5), invitations (T2.6) and ownership transfer (T2.7) are implemented, satisfying the exit criterion in `08` |
| 3 — Ticket workflow | Complete manual ticket workflow works without AI | Met — `apps/tickets` implements the models, list/create/detail, `assign`, `transition`, and messages, with the capability matrix (ADR-029), `If-Match` field edits (ADR-022), and an audit row per write; 513 tests at 98.19% coverage |

Phase 2's own criterion never mentions invitations, which is precisely why the gap went unnoticed.
The criterion is the thing to fix, not just the feature.

## 3. Endpoint traceability

Status: **implemented** · **planned** (task exists) · **unplanned** (no task) · **unspecified**
(named in the contract with no defined shape).

### Authentication and identity

| Endpoint | Plan | Backlog | Status |
|---|---|---|---|
| `GET /auth/csrf/` | T1.3 | T1.3 | implemented |
| `POST /auth/login/` | T1.3 | T1.3 | implemented |
| `POST /auth/logout/` | T1.3 | T1.3 | implemented |
| `GET /auth/me/` | T1.3 | T1.3 | implemented |
| `POST /auth/register/` (FR-001) | T2.5 | T2.5 | implemented (ADR-027) |
| `POST /invitations/preview/` (public, token in body) | T2.6 | T2.6 | implemented (ADR-026) |
| `POST /invitations/accept/` (token in body) | T2.6 | T2.6 | implemented (ADR-026) |
| `GET /api/v1/schema/` | T1.3 | T1.3 | implemented |

### Workspaces and members

| Endpoint | Plan | Backlog | Status |
|---|---|---|---|
| `GET /workspaces/` | T2.3 | T2.3 | implemented |
| `POST /workspaces/` | T2.3 | T2.3 | implemented |
| `GET /workspaces/{id}/members/` | T2.3 | T2.3 | implemented |
| `PATCH /workspaces/{id}/members/{membership_id}/` | T2.3 | T2.3 | implemented |
| `POST /workspaces/{id}/invitations/` | T2.6 | T2.6 | implemented (ADR-026) |
| `GET /workspaces/{id}/invitations/` | T2.6 | T2.6 | implemented (ADR-026) |
| `POST /workspaces/{id}/invitations/{invitation_id}/resend/` | T2.6 | T2.6 | implemented (ADR-026) |
| `DELETE /workspaces/{id}/invitations/{invitation_id}/` | T2.6 | T2.6 | implemented (ADR-026) |
| `POST /workspaces/{workspace_id}/transfer-ownership/` (owner transfer, `10_SECURITY.md`) | T2.7 | T2.7 | implemented — owner-only swap under the workspace lock (ADR-028) |

### Tickets

| Endpoint | Plan | Backlog | Status |
|---|---|---|---|
| `GET /workspaces/{id}/tickets/` | T3.2 | T3.2 | planned — filters, `ordering` allowlist, and stable pagination settled (ADR-023) |
| `POST /workspaces/{id}/tickets/` | T3.2 | T3.2 | planned |
| `GET /workspaces/{id}/tickets/{ticket_id}/` | T3.2 | T3.2 | planned |
| `PATCH /workspaces/{id}/tickets/{ticket_id}/` | T3.2 | T3.2 | planned — permitted fields, `If-Match`, and 409 settled (ADR-021, ADR-022) |
| `POST /workspaces/{id}/tickets/{ticket_id}/assign/` | T3.3 | **none** | planned, backlog gap |
| `POST /workspaces/{id}/tickets/{ticket_id}/transition/` | T3.3 | **none** | planned, backlog gap |
| `GET /workspaces/{id}/tickets/{ticket_id}/messages/` | T3.2 | T3.2 | planned |
| `POST /workspaces/{id}/tickets/{ticket_id}/messages/` | T3.2 (public) / T3.4 (internal) | T3.2; **T3.4 missing** | planned — note authority settled (ADR-021); backlog gap remains |
| `POST /workspaces/{id}/tickets/{ticket_id}/ai-draft/` | T6.4 | T6.3 (different wording) | planned |
| `GET /workspaces/{id}/tickets/{ticket_id}/ai-status/` | T6.3 | T6.2/T6.3 partially | planned |
| Audit event surface (FR-015) | T3.5 | **none** | planned, backlog gap |

### Knowledge base

| Endpoint | Plan | Backlog | Status |
|---|---|---|---|
| `GET/POST /workspaces/{id}/articles/` | T7.1 | T7.1 | planned |
| `GET/PATCH /workspaces/{id}/articles/{article_id}/` | T7.1 | T7.1 | planned |
| `POST /workspaces/{id}/articles/{article_id}/publish/` | T7.1 | T7.1 | planned |
| `POST /workspaces/{id}/articles/{article_id}/reindex/` | T7.2 | T7.2 | planned |

### SLA

| Endpoint | Plan | Backlog | Status |
|---|---|---|---|
| `GET/POST /workspaces/{id}/sla-policies/` | T8.1 | T8.1 | planned |
| `PATCH /workspaces/{id}/sla-policies/{policy_id}/` | T8.1 | T8.1 | planned |
| `GET /workspaces/{id}/escalations/` | T8.3/T8.5 | T8.2 (task only) | planned, backlog gap |
| `GET /workspaces/{id}/analytics/overview/` | — | — | **removed from the contract and declared a non-goal (ADR-025)** |
| Priority/policy change recalculates the deadline (FR-044) | **none** (inside T8.1, not stated as an acceptance criterion) | T8.1 does not cover it | **unplanned detail** |

### Operational

| Endpoint | Plan | Backlog | Status |
|---|---|---|---|
| `GET /health/live/` | T1.2 | T1.2 | implemented |
| `GET /health/ready/` | T1.2 | T1.2 | implemented (PostgreSQL only — see D-14) |

## 4. Domain entity traceability

| Entity (`03_DOMAIN_AND_DATA_MODEL.md`) | Plan | Status |
|---|---|---|
| `User` | T1.1 | implemented (`apps.accounts`) |
| `Workspace` | T2.1 | implemented |
| `Membership` | T2.1 | implemented |
| `Invitation` | T2.6 | implemented — hashed token, derived expiry, partial unique index (`0002_invitation`) |
| `Team` | **none** | **deferred past MVP (ADR-024)** — no table and no `ticket.team_id` |
| `Ticket` | T3.1 | planned — requester snapshot and `version` settled (ADR-020, ADR-022) |
| `TicketMessage` | T3.1 | planned |
| `TicketEvent`/`AuditEvent` | T3.1 (model) / T3.5 (events) | planned |
| `SLAPolicy` | T8.1 | planned |
| `EscalationRule` | T8.1/T8.3 | planned (trigger/threshold semantics unspecified) |
| `EscalationEvent` | T8.3 | planned |
| `AIJob`/`AIResult` | T5.2/T6.2 | planned |
| `KnowledgeArticle` | T7.1 | planned |
| `KnowledgeChunk` | T7.2 | planned |
| `Notification` | T8.4 | planned |

`Invitation` is the root cause of the invitations gap: the implementation plan is derived from the
entity list, so an entity that was never modelled was never scheduled. `Team` is the same defect
with a delayed fuse, because Phase 3's table references it.

## 5. Requirement traceability (`01_PRD.md`)

| Requirement | Owning task | Status |
|---|---|---|
| FR-001 secure authentication | T1.3, T2.5 | met — login/logout/me plus open registration that starts a session (ADR-027) |
| FR-002 multi-workspace, role per membership | T2.1/T2.2 | met |
| FR-003 membership and role checked on every protected operation | T2.2/T2.3, gate T2.4 | met for existing endpoints; must be re-proven per resource |
| FR-004 controlled creation/invitation | T2.3, T2.6 | met — creation is controlled; invitations are issued only by owners and admins |
| FR-005 invite/remove members by role policy | T2.3 (remove) / T2.6 (invite) | met — single-use, expiring, revocable invitations with an acceptance flow |
| FR-006 atomic ownership transfer | T2.7 | met — owner-only swap in one transaction, target promoted before the caller steps down (ADR-028) |
| FR-010/FR-011 ticket CRUD and fields | T3.1/T3.2 | planned (requester snapshot settled — ADR-020) |
| FR-012 validated assignment and transitions | T3.3 | planned (transitions per ADR-009; assignment authority settled — ADR-021) |
| FR-013/FR-014 reply vs note separation | T3.4 | planned (note authority settled — ADR-021) |
| FR-015 append-only audit stream | T3.5 | planned (vocabulary undecided — D-07) |
| FR-016 pagination, filtering, ordering | T3.2 | planned; query contract settled (ordering allowlist, `assignee`, search bounds — ADR-023) |
| FR-020–FR-027 AI assistant | T6.1–T6.6 | planned — T6.1 landed the provider adapter and the deterministic fake (ADR-034); classification, drafts, and the UI follow |
| FR-030–FR-035 knowledge base | T7.1–T7.5 | planned (T7.3 leaves full-text vs `pgvector` open) |
| FR-040–FR-045 SLA | T8.1–T8.5 | planned (FR-044 unowned — §3) |
| FR-050 health/readiness | T1.2 | met |
| FR-051 request/correlation IDs in logs | T1.2 (`apps/common/middleware.py`), T5.1 (`apps/common/tasking.py`) | met — `request_id` from the middleware, `task_id` from the correlated task base class, both on every JSON line |
| FR-052 errors observable and safe | T1.3 (`apps/common/errors.py`) | met |
| FR-053 synthetic demo data | T9.5 | planned |
| FR-054 retention and deletion | T9.6 | planned — policy documented in `10_SECURITY.md` and ADR-025; command pending |
| NFR observability (queue depth, task duration, AI latency, SLA breaches) | T5.4 (task outcome/duration) | **partly met** — structured task outcome lines plus `manage.py task_status` (T5.4); queue depth, AI latency, and SLA-breach metrics still have no owner |
| Retention/deletion policy (`10_SECURITY.md`) | T9.6 | scheduled (ADR-025) — documented now, enforcement command pending |
| Throttling on invitations, ticket creation, AI generation (`04`, `10`) | T2.5/T2.6 (auth and invitations) | registration and invitation scopes implemented; ticket and AI throttles still unowned (D-13) |

## 6. Findings

Ordered by what would hurt most if Phase 3 starts first.

**F-01 Invitations are absent at every layer (blocking).** No `Invitation` entity in `03`, no task in
`08`, no backlog entry, no payload in `04`, no email provider selected, and `MembershipStatus` only
offers `active|removed` so "pending" has nowhere to live. Three specs assume they exist anyway
(FR-005, the contract URL, `10_SECURITY.md`). **Resolved as a spec:** the entity, token lifecycle, four
workspace-side endpoints and two invitee endpoints are defined (ADR-026) and T2.6 is in `08` and `15`.
**Implemented:** `apps/organizations/invitations.py`, the `Invitation` model (migration
`organizations.0002_invitation`), and six endpoints, covered by `test_invitation_model.py`,
`test_invitation_api.py`, and `test_invitation_accept.py`.

**F-02 There is no sign-up path (blocking).** The README promises "register/sign in and create or
join a workspace"; the API has no sign-up route and the plan has no task. Invitation acceptance is
unreachable without it, since an invitee has no account. **Resolved:** `POST /auth/register/` ships in
T2.5 with tests (ADR-027).

**F-03 `Team` is referenced but never built.** `Ticket.team_id` lands in T3.1 while no task creates
teams, and the PRD's owner persona "configures teams". Either schedule it or drop the column; both
are cheap now and expensive after tickets exist. **Resolved:** teams are out of MVP and no `team_id`
is created (ADR-024).

**F-04 `analytics/overview/` has no task and no definition.** No metrics, no shape, no permission
rule. Either specify it or remove it from the contract. **Resolved:** removed, and analytics is a
declared non-goal (ADR-025).

**F-05 Backlog gaps inside the next phase.** T3.3, T3.4, and T3.5 have no entries, and the entries
that do exist restate different scopes than the plan (T6.3/T6.4, T8.2). The traceability check
proposed in §8 is the prevention.

**F-06 Throttling is complete for login only.** `REST_FRAMEWORK` declares `auth_login` as the sole
scope and settings define no `CACHES`, so throttling is per-process LocMem — ineffective across
workers. ADR-012 records this, but the contract's ticket/AI/invitation throttles have no task and
no chosen cache backend. **Partly resolved:** registration and invitation scopes are implemented
(ADR-026, ADR-027); ticket and AI throttles and the shared cache remain open (D-13).

**F-07 Phase 0's Compose scope was narrowed without a closing task.** No `Dockerfile`, no
`frontend/`, no worker or beat service. Acceptable as a deferral, but `12_CI_CD.md` items 6–10
(frontend checks, container builds) and `11_TEST_STRATEGY.md`'s container-build gate need an owner.
**Resolved for the frontend:** T4.1 owns the `frontend/` project, its CI job and the Compose dev
service; T4.11 owns the frontend gates that make item 7 real; T4.12 owns the end-to-end job (item 8);
T9.7 owns the frontend container, the bundle budget and the served artifact. Still unowned: the worker
and beat services and the backend image, which T5.1 and T9.1 carry.

**F-11 No frontend phase had design, language, or accessibility owners.** `07_FRONTEND_SPEC.md` named
routes and behaviours but no design tokens, no typography, no light/dark story, no localization or
RTL story, and no accessibility target, while `01_PRD.md` had no requirement for any of it. A UI built
from that spec would have been English-only, single-theme, and impossible to internationalize without
a rewrite. **Resolved:** the user direction is English and Arabic with RTL from the first screen, a
professional visual language, and both themes. `01_PRD.md` gains FR-060 to FR-063, `07_FRONTEND_SPEC.md`
is rewritten with a design language, an i18n/RTL section, a theming section, accessibility targets and a
bundle budget, Phase 4 is expanded from four tasks to twelve in `08`/`15`, and ADR-030/ADR-031 record
the stack and the bilingual/theming decisions.

**F-08 Requirements with no owner:** retention/deletion, owner transfer, observability metrics,
FR-044 deadline recalculation, and the security spec's "customer-facing endpoints cannot read
internal notes" test (belongs to T3.4, not yet stated there). **Partly resolved:** owner transfer is
implemented (T2.7, FR-006) and retention is T9.6 (FR-054). Still unowned: observability metrics, FR-044,
and the T3.4 read-separation test.

**F-09 Spec ambiguities that Phase 3 would otherwise invent:** `ordering`, `assignee=me`, and
searchable fields are missing from the list query string; `version` is "if needed"; permitted
`PATCH` fields for tickets are unnamed; which role may post internal notes is unstated; `SLAPolicy`
has no uniqueness rule for "one active policy per workspace+priority"; `EscalationRule.threshold`
units are undefined. **Partly resolved:** ordering/search/`assignee` (ADR-023), permitted `PATCH`
fields with `version`/`If-Match` (ADR-021, ADR-022), and internal-note authority (ADR-021) are settled.
Still open: `SLAPolicy` active-policy uniqueness and `EscalationRule.threshold` units (D-03).

**F-10 Documentation drift (low).** README says "current status: T2.3" and claims registration;
`Workspace.settings` is a schemaless blob with no consumer; `apps/organizations` has no `admin.py`,
so tenants are only inspectable through the shell.

## 7. Open decisions

Each decision is recorded as an ADR in `14_DECISIONS_AND_CHANGELOG.md` once settled. "Blocks" is the
first task that cannot be written correctly without it.

| ID | Decision | Why it blocks | Recommendation | Blocks |
|---|---|---|---|---|
| D-01 | **Settled: ADR-020.** Who is a ticket's requester? | `Ticket.requester_id` implies a `User`, but customers are explicitly not members and no portal is in scope; requiring an account per customer is a privacy and security cost | Store `requester_email` (+ name) on the ticket, with an optional FK when the requester is also a member. Keeps the portal out of MVP without inventing accounts | T3.1 |
| D-02 | Which task owns `first_response_due_at`? | The field is in the Phase 3 model; the policy that computes it is Phase 8 | Leave it nullable in T3.1, document the backfill in T8.1, and forbid writes from the API | T3.1 |
| D-03 | Uniqueness of an active `SLAPolicy` | "Select the active policy for priority *p*" is ambiguous if two rows are active | Unique constraint on `(workspace, priority)` where `is_active`, or a single-active rule per priority enforced in the service | T8.1 |
| D-04 | **Settled: ADR-021.** Ticket capability matrix | `Capability` has only `members.view/manage`; assignment, transition, and internal-note authority are unstated | Add `tickets.view/create/assign/transition/note`; allow agents to note and transition within ADR-009's table; reserve assign-to-others for manager and above | T3.1 |
| D-05 | **Settled: ADR-022.** Optimistic concurrency on tickets | Domain model says `version` "if needed"; two agents editing one ticket will collide | Use `version` + `If-Match`, return `409 conflict` on mismatch. Cheap now, painful later | T3.2 |
| D-06 | **Settled: ADR-023.** List query contract | FR-016 requires ordering; the contract lists filters only | Named allowlist: `ordering` over `updated_at`, `created_at`, `priority`, `status` (prefix `-`); `assignee=me`; `search` over subject only | T3.2 |
| D-07 | Audit event vocabulary | T3.5 needs `event_type`/`object_type` strings that stay stable across apps, and `correlation_id` source | A shared module of frozen string enums, one naming scheme reused by `AIJob.entity`; `correlation_id` from the request's ID context var, or a generated one in tasks | T3.5 |
| D-08 | **Settled: ADR-033; implemented (T5.2).** Idempotency keys | Contract says "use idempotency keys … where duplicate execution would be harmful" but names no header or store | Task-level keys only: a `TaskRecord` unique on `(task_name, idempotency_key)`, with the dispatcher deriving the key from the work. No HTTP `Idempotency-Key` header in MVP | T5.2 |
| D-09 | **Settled: ADR-026; implemented (T2.6).** Invitation lifecycle | Nothing existed (F-01) | Decided: SHA-256 hash of a 32-byte token, single-use, seven-day expiry derived from `expires_at`; statuses `pending`/`accepted`/`revoked`; roles up to `admin`; no membership row until acceptance; token carried in request bodies; `accept_path` returned once to the inviter; delivery through Django's email backend with `delivery_status`; resend rotates | T2.6 |
| D-10 | **Settled: ADR-027; implemented (T2.5).** Registration rules | FR-001 is satisfied by login only; invite acceptance needs sign-up (F-02) | Open sign-up creating an account with no workspace, plus the invite-accept flow that attaches membership. Email verification deferred with a documented limitation — which also means invitation acceptance is only as strong as unverified email ownership (ADR-026) | T2.5 |
| D-11 | **Settled: ADR-024.** Teams in or out of MVP | `tickets.team_id` exists in Phase 3; no task creates teams | Out of MVP: drop `team_id` until a team task exists. Re-add with its own migration when teams are scheduled | T3.1 |
| D-12 | **Settled: ADR-025.** MVP cut line for orphaned surfaces | Analytics, portal, owner transfer, retention were neither in the plan nor in the non-goals | Decided: analytics **out** (endpoint removed), portal **out**, owner transfer **in** as T2.7 (FR-006), retention **in** as a documented policy with T9.6 (FR-054); `01_PRD.md` §3 updated | T3.1 |
| D-13 | **Partly settled: ADR-032.** Shared cache and throttle matrix | Throttles beyond login have no task and no shared backend (F-06) | Redis `CACHES` landed in T5.1 (`DJANGO_CACHE_URL`, required in production, LocMem otherwise); the endpoint → rate → keying matrix still lives only in `04_API_CONTRACT.md`, and `10_SECURITY.md` should carry it | T2.6 |
| D-14 | Readiness policy once the broker and cache exist | Today `/health/ready/` fails only on PostgreSQL; failing on broker outage would take the API out of rotation for a degraded feature | Keep readiness to PostgreSQL; expose broker/queue health separately (and alert on backlog per `12_CI_CD.md`) | T5.1 |
| D-15 | Pull request and review policy | `12_CI_CD.md` requires "successful CI and code review" on main; work is currently committed to main and CI confirmed after the fact, so the DoD's human-review item is unenforceable | Enable branch protection with a required CI check, or record trunk-based development as an accepted deviation in ADR and drop the review requirement | immediate |
| D-16 | **Settled: ADR-030, ADR-031; specified before T4.1.** Frontend routes for auth and invitations | `07_FRONTEND_SPEC.md` had no `/register` or `/invite/:token`, and `/settings/members` had no pending-invite states | Done: both routes plus the invitation states are in `07`, the route table also names the not-found route, and the bilingual/theming requirements that constrain the router are settled. T4.1–T4.12 own the implementation | T4.1 |

## 8. Process fixes (highest leverage first)

1. **Keep a spec-to-task gate.** The single change that would have caught F-01, F-03, F-04 and F-05 is
   mechanical: a check that every endpoint in `04_API_CONTRACT.md` and every entity in
   `03_DOMAIN_AND_DATA_MODEL.md` maps to a task ID present in both `08` and `15`. It can be a test
   over the docs rather than review diligence.
2. **Write an FR row before implementing it.** Every PR names the FR/ADR it satisfies; `13_DEFINITION_OF_DONE.md`
   already requires updated specs, so this costs one line and keeps §5 current.
3. **Phase exit criteria must cite proof.** "Tenant isolation is proven by tests" should name the
   test module and the resource list; Phase 2 read as complete while half of FR-005 was absent.
4. **State MVP in/out per endpoint**, not per feature area (D-12).
5. **Backlog and plan are written in the same change** for the phase about to start, and the backlog
   entry cannot restate a different scope than the plan task (F-05).
6. **Specify before implementing**, per `08_IMPLEMENTATION_PLAN.md`'s scope rule: an endpoint listed
   in `04` without payload, errors, and permission rule is not ready to build (self-registration, T2.5, is
   the remaining example).

## 9. Recommended next order

1. ~~Settle D-01, D-04, D-05, D-06, D-11, D-12~~ — done, as ADR-020 to ADR-025, with `01`, `03`, `04`,
   `07`, `08`, `10` and `15` updated to match.
2. ~~Specify `Invitation` (D-09)~~ — done: entity, token lifecycle, four workspace-side endpoints, and two
   invitee endpoints are in `03`/`04`, with T2.6 in `08`/`15` (ADR-026).
3. ~~Specify and implement T2.5 and T2.6~~ — done: registration (ADR-027) and invitations (ADR-026)
   ship with tests and a migration.
4. ~~Implement T2.7 ownership transfer~~ — done. Write backlog entries for T3.3, T3.4, T3.5 so Phase 3
   starts with a complete queue.
5. ~~Then T3.1~~ — done. Phase 3 (T3.1–T3.5) shipped; the manual ticket workflow works end to end.
6. Phase 4 pre-flight is complete: D-16 is settled and the frontend spec, PRD, plan, backlog and CI
   specs were rewritten for a bilingual, RTL, light/dark, accessible UI before any frontend code exists.
   T4.1 starts the implementation in `08`/`15` order, and T4.12 is the phase's proof rather than a demo.

## 10. Maintenance

- Add a row when a requirement, endpoint, or entity is added anywhere in the spec set; never let a
  URL exist in `04` with no task here.
- Update **Status** in place as tasks land; append a dated note in `14_DECISIONS_AND_CHANGELOG.md`
  when a decision is settled, and change that decision's row to name its ADR.
- Re-audit at each phase boundary; keep the top "snapshot at" line honest.
