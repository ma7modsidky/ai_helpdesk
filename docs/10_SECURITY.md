# 10 — Security Requirements and Threat Model

This document is an engineering checklist, not a claim of certification or legal compliance.

## Assets
- Customer ticket content and contact details.
- Internal notes and support conversations.
- Workspace knowledge articles.
- Authentication sessions/tokens.
- LLM/API credentials.
- OAuth/provider credentials if integrations are added.
- Audit events and AI usage metadata.

## Trust boundaries
- Browser ↔ API.
- User/workspace ↔ other tenant.
- API ↔ PostgreSQL/Redis/RabbitMQ.
- Worker ↔ LLM provider/email provider.
- Ticket/article text ↔ AI model.
- CI/deployment pipeline ↔ production secrets.

## Required controls

### Authentication and authorization
- Use a maintained authentication approach; do not implement password cryptography yourself.
- Enforce role and object permissions on the server for every endpoint.
- Scope queryset access by authorized workspace before object lookup.
- Test cross-tenant access for tickets, messages, knowledge articles, AI results, and notifications.
- Protect invitations and workspace-owner transfer flows.
- Registration is open and throttled per client, and passwords go through Django's configured validators. A duplicate address is reported as a field error, which confirms that an account exists; that is accepted for MVP because the endpoint is rate limited and sign-in itself cannot be enumerated.
- Invitation tokens are random (32 bytes), single-use, stored only as a SHA-256 hash, carried in request bodies rather than URLs, and never returned by a list or detail endpoint.
- Invitation acceptance requires a signed-in account whose email equals the invited address and grants at most `admin`; ownership never travels through an invite. Without account email verification (deferred, D-10) acceptance proves only that the invitee controls an account at that address, so invitations stay revocable and short-lived.
- Revoke access promptly when membership is removed.

### Web security
- Explicitly configure allowed hosts, CORS, CSRF, cookies, HTTPS, and security headers for the chosen deployment.
- Do not use wildcard credentialed CORS.
- Apply rate limits to login, invitation, ticket creation, AI generation, and expensive search.
- Validate input lengths and types; use framework/ORM parameterization.
- The frontend bundle carries no secrets: the only build-time variable is the API base URL, and provider
  or database credentials never reach it.
- Avoid unsafe HTML rendering; sanitize rich text if supported (`dangerouslySetInnerHTML` is banned in the
  frontend by lint, and rich text is out of MVP scope).
- Session cookies are the only credential the frontend holds; no token is written to `localStorage`, so a
  script injection cannot lift one. Locale, theme, and cached responses are the only persisted client data.
- Post-login redirect targets are validated against the in-app route allowlist, so a crafted `next`
  parameter cannot bounce a user to an attacker's origin.
- The frontend surfaces the API's `request_id` for support and never renders a raw error envelope, a
  stack trace, or a request body.
- Add upload restrictions and malware scanning if file attachments are introduced.
- Do not expose debug mode or stack traces in production.

### Secrets and dependencies
- Load secrets from environment/secret manager, never source control.
- Commit `.env.example` with placeholders only.
- Rotate credentials if exposed.
- Pin and update dependencies with review; scan known vulnerabilities.
- Use least-privilege service accounts and database roles where practical.

### AI-specific controls
- Treat ticket text and knowledge documents as untrusted prompt content.
- Never allow model output to grant access or execute arbitrary actions.
- Validate structured output; allowlist enum values and source IDs.
- Human approval required before public replies.
- Minimize data sent to provider; redact sensitive fields where feasible.
- Set token/input/output limits, timeouts, retries, and workspace usage quotas.
- Do not put API keys in frontend bundles.
- Do not log full prompts or ticket bodies by default.
- Keep tenant filter in retrieval query before model context is assembled.
- Test prompt injection, source spoofing, data exfiltration attempts, and cross-tenant retrieval.

### Async and queue security
- Do not treat task IDs as authorization.
- Workers must reload and authorize/validate the target object using trusted IDs and service logic.
- Restrict broker access to private network/service credentials.
- Tasks must be idempotent where duplicate delivery is possible.
- Do not put secrets or full sensitive content in task names/log metadata.

### Audit and privacy
- Audit role changes, ticket assignment/status changes, public replies, AI draft approval/sending, and escalations.
- Ticket creation, field edits, assignment, status changes and messages are recorded in `TicketEvent`
  (ADR-029) as identifiers and field names only. Membership and invitation changes are not audited yet;
  that gap is tracked for T9.2.
- Keep audit metadata minimal and avoid secrets.
- Retention and deletion are defined below (ADR-025) and enforced by a scheduled command (FR-054).
- Use synthetic demo data.
- Restrict access to production logs and backups.

### Retention and deletion (MVP policy)
Recorded in ADR-025, enforced by T9.6. These are MVP defaults and need review before any real customer
data is stored.

| Data | Retained |
| --- | --- |
| Tickets and messages | 24 months after the ticket's last update |
| Audit events | 24 months |
| AI job payloads and results | 90 days |
| Archived workspaces | Purged 90 days after archival, by manual command |
| Backups | 30 days |

Deletion is irreversible, runs as a manual command with a `--dry-run` mode (no automatic purge in
MVP), and logs counts only — never ticket content, message bodies, or requester contact details.

## Security tests
- Cross-tenant object ID guessing returns no data.
- Agent cannot change workspace roles or owner settings.
- Internal notes cannot be read through customer-facing endpoints.
- A UI affordance never substitutes for a server check: every action offered in the browser is covered by
  the API test that refuses it for an unauthorized caller.
- The frontend bundle contains no secret, tested by the secret scan over `frontend/` and its lockfile.
- User cannot publish AI draft without appropriate permission.
- AI retrieval cannot return another workspace's article.
- Rate limit blocks abusive AI request volume.
- Error responses do not include traceback or secret material.
