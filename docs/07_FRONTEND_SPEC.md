# 07 — Frontend Specification

## Stack

React + TypeScript + Vite for a focused SPA, or Next.js if SSR/routing is a specific learning goal. For this portfolio project, React + Vite is sufficient and keeps the system simpler. Use a query/cache library only if it materially improves server-state handling; do not add state-management libraries by default.

## Main routes/screens

- `/login`
- `/register`
- `/invite/:token`
- `/app/workspaces`
- `/app/:workspaceId/inbox`
- `/app/:workspaceId/tickets/:ticketId`
- `/app/:workspaceId/knowledge`
- `/app/:workspaceId/settings/members`
- `/app/:workspaceId/settings/sla`

## Registration and invitations

- Sign-up asks for email and password, shows field-level validation, and signs the user in on success.
- An account with no workspace lands on the workspace picker with an empty state that offers
  "create a workspace" and explains that an invitation grants access to an existing one.
- `/invite/:token` shows the workspace name, the role being offered, and the invitation state before
  the user acts; it asks the user to sign in or register with the invited address when needed, and
  reports an expired invitation without pretending it can be accepted.

## Members settings

- Role changes and revocation are offered only where the server allows them; the UI mirrors 403 and
  409 instead of hiding the failure.
- Pending invitations show their state (pending, expired, accepted) with resend and revoke actions.
- Ownership transfer is offered only to the current owner, requires choosing an active member, and uses
  an explicit confirmation because the caller becomes an admin afterwards.

## Inbox

- Search, status/priority filters, assignment filter, pagination.
- Clear loading, empty, error, and retry states.
- No data from other workspaces rendered.
- Bounded page size and debounced search.

## Ticket detail

- Conversation timeline.
- Internal note and public reply modes with visually distinct labels.
- Status, priority, and assignee controls based on permissions (no team control: teams are post-MVP).
- A stale-ticket conflict (`409` from `If-Match`) is surfaced as a reload prompt, not a silent overwrite.
- AI classification panel with category, sentiment, suggested priority, and rationale.
- AI draft panel with source article links, processing status, regenerate/retry action, edit field, and explicit send action.
- SLA deadline and overdue state.
- Audit/history panel.

## Knowledge base

- Article list and editor.
- Draft/published state.
- Reindex status and errors.
- Clear warning that only published content is used for AI retrieval.

## UX and accessibility

- Keyboard navigation and visible focus.
- Labels and accessible validation errors.
- Status not conveyed by color alone.
- Confirm destructive actions.
- Avoid displaying raw backend errors.
- Handle expired authentication and permission errors.
- Never put LLM API keys or privileged credentials in frontend environment variables.
- Render AI output as text by default; sanitize if rich text/Markdown is intentionally supported.

## Frontend quality gates

- TypeScript strict mode.
- ESLint and formatter.
- Component tests for critical interactions.
- API client centralizes auth/error handling.
- Avoid duplicated domain rules in the frontend; backend remains authoritative.
