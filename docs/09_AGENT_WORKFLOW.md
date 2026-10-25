# 09 — Coding Agent Operating Procedure

## Global instructions

You are implementing ResolveAI Helpdesk from the repository's specifications.

1. Before coding, read `README.md` and the relevant docs for the requested task.
2. Do not implement features outside the task's explicit scope.
3. Do not silently change architecture, API contracts, data model invariants, or security policy.
4. If requirements conflict or are ambiguous, list the conflict and ask for a decision before coding.
5. First inspect existing code and tests; preserve working patterns unless they violate the specification.
6. Propose a brief plan and list files likely to change before implementation.
7. Implement the smallest coherent change.
8. Add/update tests for success, validation, permission denial, edge cases, and failure behavior.
9. Run relevant formatters, linters, type checks, and tests; report exact commands and outcomes.
10. Never claim a test passed unless it was actually run and passed.
11. Do not weaken/delete tests, suppress checks, or change expected behavior just to make CI green.
12. Do not add dependencies without explaining the need and maintenance/security implications.
13. Never hardcode secrets, production credentials, real customer data, or personal tokens.
14. Keep business logic out of views, serializers, Celery task wrappers, and React components when it belongs in services/domain code.
15. Update relevant docs and `14_DECISIONS_AND_CHANGELOG.md` when behavior or decisions change.

## Required task response

For each task, report:
- Scope completed
- Important design decisions
- Files changed
- Tests/checks run and actual results
- Security/performance considerations
- Known limitations
- Next task recommendation

## Task prompt template

```text
Task ID: T3.2
Goal:
Implement only the ticket list/detail API slice defined in the specifications.

Read first:
- docs/01_PRD.md
- docs/02_ARCHITECTURE.md
- docs/03_DOMAIN_AND_DATA_MODEL.md
- docs/04_API_CONTRACT.md
- docs/10_SECURITY.md
- relevant existing source and tests

Constraints:
- Preserve the modular monolith.
- Enforce tenant scope in server-side querysets/services.
- Do not expose internal notes to unauthorized roles.
- Keep views thin and validate input with serializers.
- Add tests for valid access, invalid input, and cross-tenant access.
- Do not implement unrelated features.

Before coding:
1. Summarize the relevant requirements.
2. Propose a short plan and files to change.
3. Identify ambiguities before proceeding.

After coding:
1. Run formatter, linter, type checks if relevant, and tests.
2. Report exact results without claiming unrun checks passed.
3. List any spec changes needed; do not silently make them.
```

## Context management

- Give agents only the relevant docs plus this operating procedure, not the entire repository history.
- Prefer one task per agent/branch.
- Avoid parallel agents editing the same files or migrations.
- Merge only after CI passes and a human reviews the diff.
- Ask the agent to summarize durable decisions into docs, not merely the chat.
- Use repository docs as the source of truth, not prior chat context.
