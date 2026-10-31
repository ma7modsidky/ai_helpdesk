# 11 — Testing and Quality Strategy

## Test pyramid

### Unit tests
Test pure/domain logic without network:
- Ticket status transitions.
- SLA deadline calculation and boundary cases.
- Role permission decisions.
- AI schema validation and source ID validation.
- Chunking and retrieval filtering logic.
- Idempotency key generation.

### Integration tests
Use a real test PostgreSQL database where feasible:
- Constraints and transactions.
- Tenant-scoped querysets.
- API permissions and serializers.
- Celery task state changes.
- Duplicate task delivery.

Celery runs eagerly in the test settings (`CELERY_TASK_ALWAYS_EAGER`), so `task.delay(...).get()`
executes in-process and the suite needs neither RabbitMQ nor a worker. The harness for a task test is
three pieces: `TaskRecordFactory` (or `register()`), the `captured_logs` fixture, which installs a
handler behind `RequestIdFilter` so `request_id`, `task_id`, and the structured task fields are
assertable as an aggregator would see them, and the task's own record, re-read after the call.
- Outbox publishing/consumption if implemented.

### API tests
Cover:
- Authentication required.
- Valid request/response schema.
- Validation errors.
- Pagination/filtering.
- Cross-tenant access.
- Internal note/public reply separation.
- AI endpoint returns accepted/pending rather than blocking on provider.
- Rate limiting for costly endpoints.

### Frontend component tests
Vitest with React Testing Library and jsdom, covering behaviour rather than markup:
- Loading, empty, filtered-empty, error, forbidden, and conflict states for every data screen.
- Permission-dependent affordances, including that a capability the role lacks is disabled with an
  explanation and that a server 403 is surfaced rather than swallowed.
- Public reply vs internal note mode, and that the two are never visually interchangeable.
- The `If-Match` conflict prompt preserving unsaved composer text.
- The API client's status mapping, CSRF refresh, and unsafe-redirect guard.
- Form validation errors coming from `error.details` and landing on the right field.

### Frontend internationalization tests
These guard the bilingual layer mechanically, because reviews do not catch a missing translation:
- Catalog parity: the same key set in `en` and `ar`, with no empty values and no untranslated leftovers.
- Direction matrix: each screen component renders in both `en` and `ar` with `dir` propagated.
- Formatters: the same instant and number render per locale with `latn` numerals.
- Locale resolution precedence, including an unsupported value falling back to `en`.

### Frontend accessibility tests
- `axe-core` assertions per screen component, in both directions and for the theme where colour is
  asserted.
- Keyboard and focus tests for dialogs, drawers, the composer, and the inbox list.

### End-to-end smoke tests
A short automated journey (Playwright, Chromium), run once per direction:
1. Register a new account, then sign in.
2. Create a workspace, invite a second user, and accept the invitation in a second browser context.
3. Create a ticket, assign it, reply publicly, and resolve it.
4. Assert the resolved state, the conversation treatment, and that the Arabic run has `dir="rtl"` with
   no catalog key leaking as raw text.
5. Confirm AI task status changes.
6. Review draft and source article.
7. Send public reply.
8. Verify SLA response timestamp and audit event.
9. Trigger a simulated overdue escalation.

## AI evaluation
Use a fixed, versioned set of fictional cases. Assert schema validity and key safety properties; avoid brittle exact-string assertions for generated prose. Use a fake provider for normal CI. Run optional provider-backed evaluations separately with controlled budget and no real customer data.

## Quality gates
- Formatting check.
- Lint.
- Type checking where configured.
- Unit and integration tests.
- Coverage report; set a pragmatic baseline (e.g. 80% on domain/service code) rather than gaming a global percentage.
- Migration consistency check.
- Dependency vulnerability scan.
- Secret scan.
- Frontend formatting, lint, type check, component and i18n tests, production build, and bundle budget.
- Container build.
- Optional SAST and image scan.

## Test principles
- Test behavior, not implementation details.
- A frontend test asserts what the user can see and do, so it queries by role and accessible name rather
  than by component internals or CSS class.
- Every bug fix gets a regression test.
- Security invariants need explicit negative tests.
- Do not mock the database for tests whose purpose is to validate SQL constraints or transaction behavior.
- Keep CI deterministic: fake LLM provider and no mandatory external network calls.
