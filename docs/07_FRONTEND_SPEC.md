# 07 — Frontend Specification

The frontend is a first-class deliverable, not a demo veneer: it is the surface where the product's
permission model, conflict handling, and auditability become visible. It is bilingual (English and
Arabic) with a right-to-left layout from the first screen, and it ships light and dark themes.
Stack choices are recorded in ADR-030 and ADR-031.

## 1. Stack

| Concern | Choice | Why |
| --- | --- | --- |
| Build tool | Vite | Fast dev server, native ESM, trivial CI build. |
| Framework | React + TypeScript (strict) | Specified in ADR-030; no SSR requirement, so no Next.js. |
| UI kit | Material UI (MUI) | Complete accessible component set with RTL and theming built in (ADR-030). |
| Styling engine | Emotion, with MUI's RTL stylis plugin | The documented MUI RTL path; keeps one styling system. |
| Routing | React Router (data router) | Nested layouts, route-level code splitting, loader-free usage. |
| Server state | TanStack Query | Caching, pagination, invalidation after writes, and bounded polling for AI job state (FR-024). |
| Client state | React state and context only | No global state library; the server is the source of truth. |
| i18n | i18next + react-i18next | Namespaced catalogs, interpolation, pluralisation, `dir` reporting. |
| Forms | MUI inputs plus a small validation helper on top of the API error envelope | No form library: per-field server errors are already the contract's shape. |
| Unit/component tests | Vitest + React Testing Library + jsdom (+ axe-core) | Same runner family as the build tool. |
| End-to-end tests | Playwright (Chromium) | Proves the resolve-a-ticket journey in both directions (T4.12). |
| Package manager | pnpm, with a committed lockfile | Deterministic CI installs, matching `uv.lock` on the backend. |
| Lint/format | ESLint (flat config, type-aware) + Prettier | Same discipline as the backend's ruff/mypy pair. |

### Project shape

```text
frontend/
├── src/
│   ├── app/            # providers, router, error boundary, layout shell
│   ├── components/     # reusable, product-agnostic presentational pieces
│   ├── features/       # auth, invitations, workspaces, tickets, knowledge, sla
│   ├── i18n/           # i18next setup, locale resolution, Intl formatters, catalogs
│   ├── lib/            # api client, query client, hooks, small utilities
│   └── theme/          # tokens, palette, typography, component overrides, RTL caches
├── e2e/                # Playwright journeys
└── public/
```

Rules that keep the boundary honest:

- `features/*` may import from `lib`, `components`, `theme`, and `i18n`; never from another feature's
  internals. Cross-feature reuse moves the shared part into `components` or `lib`.
- No file in `src/` imports from `e2e/`.
- `lib/api` is the only module that calls `fetch`. Everything else uses query hooks.
- Domain rules are not re-implemented here: the capability matrix, transition table, and version
  check live on the server (ADR-009, ADR-021, ADR-022). The UI renders affordances and mirrors
  refusals; it never decides legality.

## 2. Design language

The target is a calm, dense, operational tool: high information density, restrained colour, obvious
hierarchy, and no decoration that does not carry meaning. Every visual decision below is expressed as
a token so light and dark stay in step.

### 2.1 Tokens

- **Colour roles, not hex values.** Components reference semantic tokens (`background.paper`,
  `text.secondary`, `divider`, `action.hover`) and named app tokens for status. A component that
  hardcodes a colour is a review finding.
- **Brand accent:** a single primary hue used for navigation selection, primary actions, and focus.
  It must clear 4.5:1 against both `background.paper` values for text and 3:1 for the focus ring.
- **Status tokens:** `open`, `pending`, `resolved`, `closed` and `low`, `normal`, `high`, `urgent`
  each get a text/background/border triple that passes contrast in both themes. Status is always
  rendered as a chip with a **label plus an icon**, never colour alone (accessibility, §8).
- **Spacing:** the 8px grid via `theme.spacing`. Component padding uses theme spacing only.
- **Radius and elevation:** one small radius for inputs/chips, one medium for cards/panels, and
  elevation reserved for floating surfaces (dialogs, menus, drawers, snackbars). Borders, not
  shadows, separate content on the page.
- **Motion:** 120–200ms for state changes; every non-trivial transition is disabled under
  `prefers-reduced-motion: reduce`.
- **Focus:** a 2px visible focus ring on every interactive element, offset so it is not clipped by
  dense layouts. Never `outline: none` without a replacement.

### 2.2 Typography

- **Latin:** Inter Variable. **Arabic:** Noto Sans Arabic Variable. Both self-hosted through
  `@fontsource-variable/*` so the app has no runtime dependency on a font CDN and CI/E2E runs stay
  offline-safe and deterministic.
- One font stack lists both families; the two scripts are disjoint, so the browser picks the right
  face per glyph and mixed content (an Arabic subject with a Latin email address) renders correctly.
- Scale: `h1`–`h6`, `subtitle1/2`, `body1/2`, `caption`, `overline` from MUI, with weights limited to
  400/500/600/700.
- **Arabic compensation:** Arabic script needs more vertical room and no tracking. When the locale is
  `ar`, the theme raises line heights (roughly +0.15) and forces `letter-spacing: 0`, and the
  `overline` style is not used because uppercasing and tracking are Latin conventions. The locale
  switch rebuilds the theme, so this is a theme rule rather than per-component CSS.
- Numbers and dates always go through `Intl` formatters with an explicit locale (§3); numerals stay
  Western Arabic (`latn`) by deliberate choice, which is the norm in business software across the
  region.

### 2.3 Icons

- `@mui/icons-material` only. No hand-drawn SVG assets in MVP, except the logo mark.
- **Directional icons mirror in RTL**: chevrons, arrows, send, reply, indent, back navigation, and
  anything depicting motion along the inline axis. Non-directional icons (clock, user, tag, lock) do
  not mirror. Mirroring is one shared component (`DirectionalIcon`) that reads `theme.direction`, so
  the rule is applied once rather than per screen.
- Icons that stand alone as a control always carry an `aria-label` from the catalog; decorative icons
  are marked `aria-hidden`.

### 2.4 Component inventory

Built on MUI, with app-level defaults in the theme (so a screen never restates the same props):
app bar, drawer/nav rail, page header with breadcrumb, buttons (contained/outlined/text/icon),
text field, textarea, select, checkbox, radio, switch, chip (status/priority/role), badge, avatar,
list and table rows, cards and panels, tabs, tabs-within-page, dialog, confirmation dialog,
popover, menu, tooltip, alert/banner, snackbar, skeleton, progress, linear progress, pagination,
date-time display, empty-state block, error-state block, and the ticket conversation timeline.

### 2.5 State patterns (mandatory per screen)

Every data screen implements all of these; a missing state is a review finding:

| State | Treatment |
| --- | --- |
| Loading | Skeleton shaped like the content for lists and detail panels; a spinner is only for sub-second inline actions. |
| Empty | A short explanation of what will appear here plus the primary action to create it. Never a bare "no data". |
| Error | Plain-language message, a Retry action, and the request ID in a copyable line for support (never a stack trace or raw envelope). |
| Forbidden | Explains that the role lacks the capability, names the required role, and ends there. Offered only where the server agrees. |
| Conflict | `409` on a ticket edit or command becomes an explicit "this ticket changed" prompt with a reload action (§7). |
| Offline/throttled | `429` shows when to retry; a dropped connection shows a retry affordance without losing typed input. |

Long-running work never blocks the UI: a mutation disables its own control and shows progress in
place rather than a full-page spinner.

## 3. Internationalization and RTL

Supported locales: **`en` (LTR)** and **`ar` (RTL)**. Additional locales are out of MVP scope, but
nothing may assume exactly two.

### 3.1 Copy and catalogs

- All user-visible copy lives in a catalog per locale (`src/i18n/locales/en.json`, `ar.json`). A
  hardcoded string in a component is a review finding — including `aria-label`s, `title`s, and
  empty-state text.
- Keys are grouped by feature area inside the catalog (`common.*`, `auth.*`, `workspaces.*`,
  `invitations.*`, `tickets.*`, `errors.*`, `a11y.*`). Catalogs load with the bundle in MVP because they
  are small; splitting them into lazy-loaded i18next namespaces is allowed when the bundle budget
  requires it, and that is the only reason to split them.
- Keys are semantic (`tickets.inbox.filters.unassigned`), never English sentences. Interpolation goes
  through `{{value}}`; user-controlled text is never used as a key.
- **Arabic is Modern Standard Arabic**, first person and neutral in tone, with product terminology
  consistent across screens (`ticket` → تذكرة, `workspace` → مساحة عمل, `agent` → موظف الدعم).
- Dates, numbers, and relative times use `Intl` through shared formatters with the active locale;
  no component formats dates itself.
- A **catalog-parity test** fails when a key exists in one locale and not the other, so a missing
  translation cannot ship silently.

### 3.2 Locale resolution and persistence

Client-only (ADR-031); the API stores no locale.

1. `?lang=` query parameter, if it is a supported locale.
2. `localStorage["resolveai.locale"]`, if supported.
3. `navigator.languages`, first supported match by language subtag.
4. Fallback `en`.

The resolved locale is written back to `localStorage`, and a `?lang=` value is preserved in the URL
long enough to survive the first render. A language switcher in the app bar and on the auth screens
changes it at runtime with no reload.

### 3.3 Direction

Three things change together, and the code that changes them lives in one provider:

- `<html lang>` and `<html dir>` are updated for the active locale.
- MUI's theme is rebuilt with `direction: 'rtl' | 'ltr'`, which drives component internals (drawer
  anchor, tabs scrolling, autocomplete placement, transitions).
- The Emotion cache swaps to the RTL one (`@mui/stylis-plugin-rtl` plus `stylis`'s `prefixer`), which
  flips the physical CSS that MUI and app styles generate.

Engineer rules for app code:

- Use **logical** properties: `marginInlineStart/End`, `paddingInlineStart/End`,
  `insetInlineStart/End`, `borderInlineStart`, `textAlign: 'start' | 'end'`. `left`/`right`/`marginLeft`
  in a new component is a review finding unless it is deliberately physical (for example a fixed
  scrollbar gutter).
- Never use `dir="rtl"` attributes as a layout hack, and never fork a component per direction. If a
  layout needs to know the direction, it reads `theme.direction` or the `useDirection()` hook.
- Mirror directional icons (§2.3) and direction-sensitive illustrations; keep timestamps, numbers,
  and code-like values in the same visual order in both directions.
- Watch the known RTL trap list when reviewing: drawer anchors, tab indicators, tooltip and menu
  placement, absolute positioning, box shadows, progress direction, pagination arrows, gradient
  direction, and scrollbar behaviour.

### 3.4 Testing the bilingual layer

- The catalog-parity test above.
- A direction-matrix test: every screen component renders in both `en` and `ar` without crashing and
  with `dir` propagated, driven by a small test helper rather than per-test setup.
- A formatter test asserting the same instant renders differently in `en` and `ar` and that numerals
  stay `latn`.
- The Playwright journey (T4.12) runs once per direction, which is what actually catches layout
  breakage the component tests cannot see.

## 4. Theming

- Light and dark are both shippable, defined together with MUI's `colorSchemes` API over CSS theme
  variables, so tokens are declared once and mode switching does not re-render the tree.
- The default mode follows the operating system (`defaultMode="system"`); a three-state control
  (system/light/dark) sits in the app bar and its choice persists.
- **No flash of the wrong theme:** `index.html` contains a tiny inline script that applies the stored
  mode to the document before the bundle runs. Because the app is client-rendered, MUI's SSR script
  does not apply.
- Both modes must pass contrast checks (§8); a colour that only works in one mode is a bug, not a
  preference.
- Theme-scoped overrides live in `src/theme/components.ts` so screens compose rather than restyle.

## 5. Routes

| Route | Screen | Access |
| --- | --- | --- |
| `/login` | Sign in | Public (redirects to the app when already signed in). |
| `/register` | Sign up | Public; lands signed in with no workspace. |
| `/invite/:token` | Invitation preview and acceptance | Public preview; acceptance requires a signed-in account whose email matches. |
| `/app/workspaces` | Workspace picker | Authenticated. |
| `/app/:workspaceId/inbox` | Ticket inbox | Member of that workspace. |
| `/app/:workspaceId/tickets/:ticketId` | Ticket detail | Member of that workspace. |
| `/app/:workspaceId/knowledge` | Knowledge base | Member; editing requires the publish capability (Phase 7). |
| `/app/:workspaceId/settings/members` | Members and invitations | Member; controls require `members.manage`. |
| `/app/:workspaceId/settings/sla` | SLA policies | Member; editing requires `members.manage` (Phase 8). |
| `*` | Not found | Public. |

- The workspace id in the URL is a **hint, not an authorization**: the API answers 404 for a
  workspace the user cannot see, and the UI renders that as "workspace not found" after clearing the
  cached workspace list. Switching workspaces rewrites the URL rather than keeping hidden state.
- **Inbox query state lives in the URL** (`status`, `priority`, `assignee`, `search`, `ordering`,
  `page`) so a view is shareable, reload-safe, and back-button correct. The URL carries only
  allowlisted values (§7).
- Route-level code splitting: the shell and auth screens are in the initial bundle; inbox, ticket
  detail, settings, and knowledge screens are lazy-loaded.

## 6. Screens

### 6.1 Authentication

- Sign-in and sign-up ask for email and password, show field-level validation from
  `error.details`, and disable submission while in flight.
- Sign-up signs the user in on success and lands on the workspace picker with an empty state that
  offers "create a workspace" and explains that an invitation grants access to an existing one
  (ADR-027).
- Password rules come from the server's validators; the UI states them and never re-implements them.
- An expired or revoked session is detected centrally, lands on `/login` with a short explanation,
  and returns to the attempted route afterwards.
- Both screens carry the language and theme controls, because they are the first thing a new user
  sees.

### 6.2 Invitation acceptance

- `/invite/:token` calls the public preview endpoint and shows the workspace name, the offered role,
  and the invitation state **before** the user acts.
- An unauthenticated visitor is asked to sign in or register **with the invited address**; a signed-in
  visitor whose email differs is told so explicitly and offered a way to switch account.
- Expired, revoked, already-accepted, and unknown tokens each get their own honest message — never a
  generic failure, and never a button that cannot succeed.
- Acceptance lands inside the workspace at the inbox.

### 6.3 Workspace picker and application shell

- The picker lists every workspace with its name, slug, timezone, and status, offers workspace
  creation, and has an empty state for an account with no memberships. The workspace resource does not
  carry the caller's role, so the role shown after entering a workspace comes from that workspace's
  member list; including the caller's role in the workspace row is recorded as a candidate API
  refinement rather than assumed here.
- The shell provides the app bar (workspace switcher, global search entry when it lands, language,
  theme, user menu) and a navigation rail/drawer with Inbox, Tickets and, per phase, Knowledge and
  Settings. Navigation is built from a single route table so an added route cannot be missing from
  the nav.
- The shell renders a workspace-level breadcrumb and keeps the workspace context visible, so the user
  can always tell which tenant they are in.
- A workspace that has been archived or that the user no longer belongs to resolves to the picker with
  an explanation, not a broken layout.

### 6.4 Members and invitations

- Member list with role, status, and join date; role changes and revocation are offered only where the
  capability matrix allows them, and the UI mirrors a 403 or 409 instead of hiding the failure.
- The last-owner rule is surfaced as an explanation when a demotion is refused.
- Invitations show pending, expired, and accepted states with resend and revoke actions; the accept
  link is shown **once** at creation time with a copy action, and is never displayed again (ADR-026).
- Ownership transfer is offered only to the current owner, requires choosing an active member, and uses
  an explicit confirmation that states the caller becomes an admin.

### 6.5 Inbox

- Filters: status, priority, assignee (`me`, `unassigned`, member), free-text search on subject, and an
  ordering control over the server's allowlist. Search is debounced (300ms) and typed into the URL.
- Rows show subject, requester, status and priority chips, assignee, and last update, with a relative
  time and the absolute value on hover.
- Pagination is server-driven with the contract's bounded page size; the page count comes from `count`.
- Skeleton/empty/error/retry states per §2.5; an empty result after filtering is distinguished from a
  workspace with no tickets and offers to clear the filters.
- Keyboard: the list is navigable, `Enter` opens a ticket, and focus visible throughout.

### 6.6 Ticket detail

- Header: subject, status, priority, assignee, requester contact, created/updated times, and a
  breadcrumb back to the inbox.
- Conversation timeline shows public replies and internal notes with distinct labels, icons, and
  background treatment, and never blurs the distinction (FR-014). The composer makes the mode
  explicit and does not default silently to either.
- Field controls (status, priority, assignee) are disabled or hidden per the capability matrix and
  send the ADR-022 write shapes: `PATCH` with `If-Match` for fields, commands for assignment and
  transitions.
- A stale `If-Match` conflict is surfaced as a "this ticket changed" prompt that offers to reload the
  latest version; unsaved composer text is preserved. Silent overwrite is never offered.
- The audit/history panel lists `TicketEvent` rows for the ticket when the endpoint lands.
- SLA deadline and AI panels are added by their own phases (T8.5, T6.4) rather than stubbed here.

### 6.7 Knowledge base (Phase 7, T7.6) and SLA settings (Phase 8, T8.5)

Listed in the plan with their own acceptance criteria: article list/editor with draft and published
state, reindex status and errors, a clear warning that only published content feeds AI retrieval; SLA
policy editing per priority with validation against the deadline rules, and the manager escalation
view.

## 7. API integration

### 7.1 One client

`src/lib/api/client.ts` is the only place `fetch` is called. It:

- sends `credentials: 'include'` (session cookie authentication) and `Content-Type: application/json`;
- attaches `X-CSRFToken` from the CSRF bootstrap (`GET /api/v1/auth/csrf/`) to every state-changing
  request, refreshing the token when the API rejects it;
- builds URLs from `VITE_API_BASE_URL` (empty by default, meaning same-origin through the Vite dev
  proxy or the reverse proxy in deployment) plus the `/api/v1` prefix;
- parses the uniform error envelope into a typed `ApiError { status, code, message, requestId, details }`
  and normalises network failures and non-JSON responses into the same type;
- never logs request or response bodies; it surfaces `requestId` for support.

### 7.2 Status-code behaviour

| Status | Behaviour |
| --- | --- |
| `400` | Field errors go to the matching form controls; unknown fields are shown at form level. |
| `401` | Clear session state, redirect to `/login?next=…`, one short banner explaining expiry. |
| `403` | The action is not permitted: explain which role is required, refresh the workspace context. |
| `404` | Render the route's not-found state; for a workspace, return to the picker. |
| `409` | Route to the owning flow: `version` conflicts in ticket editing, duplicate-invitation and last-owner conflicts in settings. |
| `429` | Show the retry window from the response when available; never auto-retry a throttled write. |
| `5xx` | Generic message plus the request ID, with a retry that is safe because the writes are commands. |

### 7.3 Server state

- TanStack Query with a documented key scheme: `['session']`, `['workspaces']`,
  `['workspace', id]`, `['tickets', workspaceId, query]`, `['ticket', workspaceId, ticketId]`.
  Workspace-scoped keys always include the workspace id so switching tenants cannot serve another
  workspace's cache entry.
- `staleTime` 30s for lists, 0 for the session; retries limited to idempotent reads, never for writes.
- Writes invalidate the narrowest set of keys (a ticket mutation invalidates that ticket and the
  ticket lists for the workspace), and the response body is written into the cache where the contract
  returns the updated representation.
- Polling is opt-in and bounded: a query that polls a job status stops on a terminal state and on
  component unmount. Never poll a mutating endpoint.

### 7.4 Permissions in the UI

The backend is authoritative. The UI derives affordances from the caller's own role, which it reads
from the workspace member list, and treats a 403 as the final answer rather than retrying. Disabled
controls carry a tooltip that names the requirement; the frontend never invents a rule the API does
not enforce, and never treats a hidden control as a security boundary.

## 8. Accessibility

Target **WCAG 2.2 AA** for every screen, in both languages and both themes.

- Semantic HTML first; ARIA only to fill gaps. Landmarks (`header`, `nav`, `main`), one `h1` per page,
  and a heading order that does not skip levels.
- Full keyboard operation: every interactive element is reachable and operable, the focus ring is
  visible, the focus order follows the visual order, and dialogs/drawers trap and restore focus.
- Contrast: 4.5:1 for body text, 3:1 for large text and UI boundaries, verified in light and dark.
- Status and priority use label plus icon, never colour alone.
- Form controls have persistent visible labels (placeholders are not labels); validation errors are
  programmatically associated and announced through a polite live region.
- A skip-to-content link precedes the shell navigation.
- The active language is exposed through `lang` so screen readers and hyphenation choose the right
  rules; mixed-direction strings inside a message are wrapped in `bdi` where the content is
  user-supplied (a ticket subject or requester name).
- `prefers-reduced-motion` disables transitions; no content is conveyed by animation.
- Touch and pointer targets meet the 24px minimum with 44px as the design default.

## 9. Performance

- Route-level code splitting; the initial bundle contains the shell, auth, and picker only.
- **Budget:** initial JavaScript ≤ 350 KB gzip and each lazy route ≤ 150 KB gzip, enforced by a build
  check in T9.7 and reported in CI. MUI is imported by path so unused components are not bundled.
- Skeletons instead of blocking spinners; optimistic UI only where a rollback is safe (none in MVP).
- Search debounced at 300ms; filters applied on the server, never by filtering a full list client-side.
- No list virtualisation until measurement shows a need; the API's page size bounds the DOM.
- Images: none in MVP except the logo, which is inline SVG.

## 10. Security

- The frontend bundle contains **no secrets**: the only build-time variable is `VITE_API_BASE_URL`.
  LLM provider keys, database credentials, and email credentials are backend-only.
- Everything from the API is untrusted text: React escapes by default, and `dangerouslySetInnerHTML` is
  banned (ESLint-enforced). Rich text is out of MVP scope; if Markdown is ever rendered, it must go
  through an allowlist sanitiser in the same change.
- AI output is rendered as text, labelled as a suggestion, and never auto-sent (FR-022, FR-027).
- The app never logs ticket bodies, message text, requester contact details, or credentials to the
  console; it surfaces request IDs instead.
- Authentication is a session cookie, so the app does no token storage of its own (no `localStorage`
  tokens, which is what makes XSS impact tolerable in the meantime).
- Deep links are validated against the route allowlist before redirect, so `/login?next=` cannot bounce
  a user to an external origin.

## 11. Frontend quality gates

- TypeScript strict, plus `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, and
  `noImplicitOverride`.
- ESLint (type-aware, flat config) with the React hooks rules, the `dangerouslySetInnerHTML` ban, and
  the no-hardcoded-string rule for user-visible copy; Prettier formatting check.
- Vitest component tests for critical interactions, including role-dependent affordances, loading,
  empty, and error states, and the 409 conflict flow.
- `axe-core` assertions on every screen component in both directions, plus keyboard/focus tests.
- Catalog parity between `en` and `ar`, and a direction-matrix render test (§3.4).
- Production build succeeds and stays within the bundle budget.
- Playwright journey (T4.12) covering register → workspace → invite → ticket → resolve in LTR and RTL.

## 12. Out of scope for MVP

Server-side rendering or Next.js; native mobile shells; locales beyond `en` and `ar`; a bespoke
component library beyond theme-level MUI customisation; rich-text editing, file attachments, and
Markdown rendering; charts and analytics dashboards (ADR-025); WebSocket/live updates (polling is
sufficient); offline-first behaviour and service workers; virtualised lists; and drag-and-drop ticket
management.
