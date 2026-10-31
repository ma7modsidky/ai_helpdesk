import { expect, test } from '@playwright/test';

import { readSeedState } from './seed';
import { signIn, UI_COPY } from './support';

/**
 * The journey runs against a seeded backend (T4.12), so this reads what the seed created:
 * a workspace with a queue in it, reachable by its own account, and a server-side filter
 * that narrows the list. It is also the tenant-isolation check a browser can make — the
 * account created by the journey never appears in this workspace.
 */
test.describe('the seeded backend', () => {
  test('shows the seeded queue and filters it server-side', async ({ browser }) => {
    const state = await readSeedState();
    const copy = UI_COPY.en;

    const context = await browser.newContext();
    const page = await context.newPage();

    try {
      await page.goto('/login?lang=en');
      await signIn(page, copy, state.ownerEmail, state.ownerPassword);

      await expect(page.getByRole('heading', { name: copy.workspaces })).toBeVisible();
      await page.getByRole('button', { name: new RegExp(state.workspaceName) }).click();

      await expect(page.getByRole('heading', { name: copy.tickets })).toBeVisible();
      for (const subject of state.ticketSubjects) {
        await expect(page.getByRole('link', { name: subject })).toBeVisible();
      }

      // The filter is a server query, so a filtered view is a new request rather than a
      // client-side narrowing of whatever happened to be loaded.
      await page.locator('#inbox-status').click();
      await page.getByRole('option', { name: copy.resolved }).click();

      await expect(page.getByRole('link', { name: state.ticketSubjects[2] })).toBeVisible();
      await expect(page.getByRole('link', { name: state.ticketSubjects[0] })).toHaveCount(0);

      // The resolved ticket opens with its conversation.
      await page.getByRole('link', { name: state.ticketSubjects[2] }).click();
      await expect(page.getByText(copy.resolved).first()).toBeVisible();
      await expect(
        page.getByText('We have sent a fresh reset link to the address on the account.'),
      ).toBeVisible();
    } finally {
      await context.close();
    }
  });
});
