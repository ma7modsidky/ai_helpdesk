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

### Frontend tests
Cover:
- Inbox loading/empty/error states.
- Permission-dependent actions.
- Public reply vs internal note mode.
- AI draft status and retry.
- Explicit human approval before sending.
- Accessible labels and validation feedback.

### End-to-end smoke tests
A short automated or documented smoke journey:
1. Log in as seeded admin.
2. Create/open ticket.
3. Confirm AI task status changes.
4. Review draft and source article.
5. Send public reply.
6. Verify SLA response timestamp and audit event.
7. Trigger a simulated overdue escalation.

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
- Frontend production build.
- Container build.
- Optional SAST and image scan.

## Test principles
- Test behavior, not implementation details.
- Every bug fix gets a regression test.
- Security invariants need explicit negative tests.
- Do not mock the database for tests whose purpose is to validate SQL constraints or transaction behavior.
- Keep CI deterministic: fake LLM provider and no mandatory external network calls.
