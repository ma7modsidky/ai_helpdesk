import { expect, test } from '@playwright/test';

import {
  expectDirection,
  expectMirroredFrame,
  expectNoRawCatalogKeys,
  registerAccount,
  UI_COPY,
  uniqueEmail,
  type JourneyLocale,
} from './support';

/**
 * The phase's exit criterion, through a browser (T4.12).
 *
 * One account registers, creates a workspace, invites a second person, and resolves a
 * ticket; the second person accepts the invitation in a separate browser context, which is
 * the only way to prove the invitation works for somebody who is not the inviter. It runs
 * once per direction, because RTL breakage lives in layout rather than in components.
 */
const PASSWORD = 'e2e-journey-password-1';
const LOCALES: readonly JourneyLocale[] = ['en', 'ar'];

for (const locale of LOCALES) {
  const direction = locale === 'ar' ? 'rtl' : 'ltr';
  const copy = UI_COPY[locale];

  test.describe(`the resolve-a-ticket journey (${locale})`, () => {
    test('register → workspace → invite → accept → ticket → assign → reply → resolve', async ({
      browser,
    }) => {
      const ownerEmail = uniqueEmail(`owner.${locale}`);
      const inviteeEmail = uniqueEmail(`invitee.${locale}`);
      const workspaceName = `Journey ${locale}`;
      const subject = `Charged twice ${locale}`;

      const ownerContext = await browser.newContext();
      const owner = await ownerContext.newPage();
      const inviteeContext = await browser.newContext();
      const invitee = await inviteeContext.newPage();

      try {
        // 1. Register. `?lang=` sets the language on the first paint, before any interaction.
        await owner.goto(`/register?lang=${locale}`);
        await expectDirection(owner, direction);
        await registerAccount(owner, copy, ownerEmail, PASSWORD);

        // 2. Create the workspace; the caller becomes its owner and lands in its inbox.
        await expect(owner.getByRole('heading', { name: copy.workspaces })).toBeVisible();
        await owner.getByRole('button', { name: copy.createWorkspace }).click();
        const createWorkspace = owner.getByRole('dialog');
        await createWorkspace.locator('#workspace-name').fill(workspaceName);
        await createWorkspace
          .locator('#workspace-slug')
          .fill(`journey-${locale}-${Date.now().toString().slice(-6)}`);
        await createWorkspace.getByRole('button', { name: copy.create }).click();

        await expect(owner.getByRole('heading', { name: copy.tickets })).toBeVisible();
        await expect(owner.getByText(copy.noTickets)).toBeVisible();

        // 3. Invite the second person and take the accept link, which is shown once.
        await owner.getByRole('link', { name: copy.members }).click();
        await owner.getByRole('button', { name: copy.invite }).click();
        const inviteDialog = owner.getByRole('dialog');
        await inviteDialog.locator('#invite-email').fill(inviteeEmail);
        await inviteDialog.getByRole('button', { name: copy.inviteSubmit }).click();

        const acceptPath = await owner.getByText('/invite/').innerText();
        await owner.getByRole('button', { name: copy.done }).click();

        // 4. Accept in a second session: register the invited address, then accept. The
        // language is resolved once and remembered, so every screen from the invitation
        // onwards stays in the direction the invitee arrived in.
        await invitee.goto(`${acceptPath}?lang=${locale}`);
        await invitee.getByRole('link', { name: copy.createAccount }).click();
        await registerAccount(invitee, copy, inviteeEmail, PASSWORD);
        await expect(invitee.getByRole('button', { name: copy.accept })).toBeVisible();
        await invitee.getByRole('button', { name: copy.accept }).click();

        // 5. Back to the queue, and create a ticket. The member the invitee just became has
        // to be assignable already, which the screen gets by re-reading the member list when
        // it mounts rather than trusting a page cached before the invitation was accepted.
        await expect(invitee.getByRole('heading', { name: copy.tickets })).toBeVisible();
        await owner.getByRole('link', { name: copy.tickets }).click();
        await owner.getByRole('button', { name: copy.newTicket }).click();
        const createTicket = owner.getByRole('dialog');
        await createTicket.locator('#ticket-subject').fill(subject);
        await createTicket
          .locator('#ticket-description')
          .fill('My statement shows two charges for the same month.');
        await createTicket.locator('#ticket-requester-email').fill('journey.customer@example.com');
        await createTicket.getByRole('button', { name: copy.create }).click();
        await expect(owner.getByRole('heading', { name: subject })).toBeVisible();

        // 6. Assign it to the person who accepted the invitation.
        await owner.locator('#ticket-assignee').click();
        await owner.getByRole('option', { name: inviteeEmail }).click();

        // 7. Reply publicly. The mode is chosen explicitly — nothing sends by default.
        await owner.getByRole('button', { name: copy.publicReply }).click();
        await owner.locator('#ticket-message').fill('The duplicate charge has been refunded.');
        await owner.getByRole('button', { name: copy.send }).click();
        await expect(owner.getByText('The duplicate charge has been refunded.')).toBeVisible();

        // 8. Resolve it.
        await owner.locator('#ticket-status').click();
        await owner.getByRole('option', { name: copy.resolved }).click();
        await expect(owner.getByText(copy.resolved).first()).toBeVisible();

        // 9. The screen the invitee sees is the same ticket, with the reply on it. Their
        // window has been open since before the ticket existed, and nothing pushes a change
        // to it, so the step that opens the queue is a reload — which also proves the
        // session comes back from the session endpoint rather than from in-memory state.
        await invitee.reload();
        await expect(invitee.getByRole('link', { name: subject })).toBeVisible();
        await invitee.getByRole('link', { name: subject }).click();
        await expect(invitee.getByText('The duplicate charge has been refunded.')).toBeVisible();

        // 10. The bilingual invariants the component tests cannot check.
        await expectDirection(owner, direction);
        await expectMirroredFrame(owner, direction);
        await expectNoRawCatalogKeys(owner);
        await expectNoRawCatalogKeys(invitee);
      } finally {
        await ownerContext.close();
        await inviteeContext.close();
      }
    });
  });
}
