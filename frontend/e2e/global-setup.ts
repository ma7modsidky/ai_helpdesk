import { seedBackend, waitForApi, writeSeedState } from './seed';

/**
 * Prepare the backend once per run: wait until the API answers readiness, then seed the
 * demo workspace through the public contract (T4.12). A journey that cannot reach the API
 * fails here with an actionable message instead of timing out inside a browser step.
 */
export default async function globalSetup(): Promise<void> {
  const apiOrigin = process.env['E2E_API_ORIGIN'] ?? 'http://127.0.0.1:8000';
  await waitForApi(apiOrigin);
  await writeSeedState(await seedBackend(apiOrigin));
}
