import { defineConfig, devices } from '@playwright/test';

/**
 * The end-to-end configuration (T4.12).
 *
 * The journey drives the real SPA against a real API on the same origin, so the dev server
 * proxies `/api` to Django exactly as development and deployment do. Retries stay at zero:
 * the point of the job is that a failing or flaky journey blocks the pipeline, and an
 * automatic retry would hide exactly that. Traces are kept when a run fails, which is the
 * artefact needed to diagnose it.
 */
const baseURL = process.env['E2E_BASE_URL'] ?? 'http://127.0.0.1:5173';

// A caller that points the suite at an already-running deployment does not need a dev
// server started underneath it.
const externalServer = Boolean(process.env['E2E_BASE_URL']);

export default defineConfig({
  testDir: './e2e',
  // The journey creates workspaces and invites people, so specs run one at a time.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env['CI']),
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    // An action waits for its element to be actionable, and the default is no timeout of
    // its own: a step addressed in the wrong language used to hang until the test timed
    // out rather than reporting the missing element. Bounded actions fail with the locator.
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  ...(externalServer
    ? {}
    : {
        webServer: {
          command: 'pnpm dev --host 127.0.0.1',
          url: baseURL,
          reuseExistingServer: !process.env['CI'],
          timeout: 120_000,
        },
      }),
});
