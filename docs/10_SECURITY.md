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
- Test cross-tenant access for tickets, messages, knowledge articles, AI results, notifications, analytics, and exports.
- Protect invitations and workspace-owner transfer flows.
- Revoke access promptly when membership is removed.

### Web security
- Explicitly configure allowed hosts, CORS, CSRF, cookies, HTTPS, and security headers for the chosen deployment.
- Do not use wildcard credentialed CORS.
- Apply rate limits to login, invitation, ticket creation, AI generation, and expensive search.
- Validate input lengths and types; use framework/ORM parameterization.
- Avoid unsafe HTML rendering; sanitize rich text if supported.
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
- Keep audit metadata minimal and avoid secrets.
- Define retention/deletion behavior and document it.
- Use synthetic demo data.
- Restrict access to production logs and backups.

## Security tests
- Cross-tenant object ID guessing returns no data.
- Agent cannot change workspace roles or owner settings.
- Internal notes cannot be read through customer-facing endpoints.
- User cannot publish AI draft without appropriate permission.
- AI retrieval cannot return another workspace's article.
- Rate limit blocks abusive AI request volume.
- Error responses do not include traceback or secret material.
