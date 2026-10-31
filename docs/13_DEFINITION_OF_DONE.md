# 13 — Definition of Done

A task is complete only when all applicable items are true:

- [ ] Acceptance criteria in the spec are satisfied.
- [ ] Implementation stays within the requested scope.
- [ ] Permissions and tenant isolation are enforced server-side.
- [ ] Relevant success, invalid-input, denial, edge-case, and failure tests exist.
- [ ] Tests were run and actual outcomes reported.
- [ ] Formatting, linting, and type checks pass where configured.
- [ ] No secrets or real personal data are committed.
- [ ] Logs/errors do not leak sensitive data.
- [ ] Query patterns and indexes are reasonable for expected access paths.
- [ ] UI work: the loading, empty, error, forbidden, and conflict states for the affected screen exist
      and are tested; every user-visible string — including labels, placeholders, `aria-label`s, and
      empty-state copy — comes from the `en` and `ar` catalogs; the screen renders correctly in both
      directions and both themes.
- [ ] UI work: keyboard operation, visible focus, programmatic labels, and an `axe-core` assertion cover
      the new or changed screen.
- [ ] Frontend work: formatting, lint, type check, tests, and the production build pass, and the change
      stays within the bundle budget.
- [ ] API/UI behavior and error states are documented.
- [ ] Relevant specs and decisions are updated.
- [ ] No unrelated refactor or dependency was slipped in.
- [ ] A human has reviewed the diff.
