# 07 — Frontend Specification

## Stack

React + TypeScript + Vite for a focused SPA, or Next.js if SSR/routing is a specific learning goal. For this portfolio project, React + Vite is sufficient and keeps the system simpler. Use a query/cache library only if it materially improves server-state handling; do not add state-management libraries by default.

## Main routes/screens

- `/login`
- `/app/workspaces`
- `/app/:workspaceId/inbox`
- `/app/:workspaceId/tickets/:ticketId`
- `/app/:workspaceId/knowledge`
- `/app/:workspaceId/analytics`
- `/app/:workspaceId/settings/members`
- `/app/:workspaceId/settings/sla`

## Inbox

- Search, status/priority filters, assignment filter, pagination.
- Clear loading, empty, error, and retry states.
- No data from other workspaces rendered.
- Bounded page size and debounced search.

## Ticket detail

- Conversation timeline.
- Internal note and public reply modes with visually distinct labels.
- Status, priority, team, and assignee controls based on permissions.
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
