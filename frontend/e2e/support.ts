import { expect, type Page } from '@playwright/test';

/**
 * Shared steps and assertions for the end-to-end journey.
 *
 * The copy is read from the same catalogs the app renders, per language, because an
 * end-to-end test that looked elements up by CSS class would pass while the screen showed
 * the wrong words. Fields are addressed by their `id`, which is language-independent.
 */

export type JourneyLocale = 'en' | 'ar';

export interface UiCopy {
  readonly signIn: string;
  readonly createAccount: string;
  readonly registerSubmit: string;
  readonly workspaces: string;
  readonly createWorkspace: string;
  readonly create: string;
  readonly tickets: string;
  readonly members: string;
  readonly invite: string;
  readonly inviteSubmit: string;
  readonly done: string;
  readonly accept: string;
  readonly newTicket: string;
  readonly noTickets: string;
  readonly send: string;
  readonly publicReply: string;
  readonly resolved: string;
}

export const UI_COPY: Record<JourneyLocale, UiCopy> = {
  en: {
    signIn: 'Sign in',
    createAccount: 'Create one',
    registerSubmit: 'Create account',
    workspaces: 'Your workspaces',
    createWorkspace: 'Create workspace',
    create: 'Create',
    tickets: 'Tickets',
    members: 'Members',
    invite: 'Invite someone',
    inviteSubmit: 'Create invitation',
    done: 'Done',
    accept: 'Accept invitation',
    newTicket: 'New ticket',
    noTickets: 'No tickets yet',
    send: 'Send',
    publicReply: 'Public reply',
    resolved: 'Resolved',
  },
  ar: {
    signIn: 'دخول',
    createAccount: 'أنشئ حسابًا',
    registerSubmit: 'إنشاء الحساب',
    workspaces: 'مساحات العمل',
    createWorkspace: 'إنشاء مساحة عمل',
    create: 'إنشاء',
    tickets: 'التذاكر',
    members: 'الأعضاء',
    invite: 'دعوة عضو',
    inviteSubmit: 'إنشاء الدعوة',
    done: 'تم',
    accept: 'قبول الدعوة',
    newTicket: 'تذكرة جديدة',
    noTickets: 'لا توجد تذاكر بعد',
    send: 'إرسال',
    publicReply: 'رد عام',
    resolved: 'تم الحل',
  },
};

/** A fictional address, unique per run so two runs cannot collide on one database. */
export function uniqueEmail(prefix: string): string {
  return `${prefix}.${Date.now()}.${Math.floor(Math.random() * 1000)}@example.com`;
}

/** Fill the registration form and submit it (the account is signed in on success). */
export async function registerAccount(
  page: Page,
  copy: UiCopy,
  email: string,
  password: string,
): Promise<void> {
  await page.locator('#register-email').fill(email);
  await page.locator('#register-password').fill(password);
  await page.getByRole('button', { name: copy.registerSubmit }).click();
}

export async function signIn(
  page: Page,
  copy: UiCopy,
  email: string,
  password: string,
): Promise<void> {
  await page.locator('#login-email').fill(email);
  await page.locator('#login-password').fill(password);
  await page.getByRole('button', { name: copy.signIn }).click();
}

/** The document direction the locale requires, asserted on the `html` element itself. */
export async function expectDirection(page: Page, direction: 'ltr' | 'rtl'): Promise<void> {
  await expect(page.locator('html')).toHaveAttribute('dir', direction);
  await expect(page.locator('html')).toHaveAttribute('lang', direction === 'rtl' ? 'ar' : 'en');
}

/**
 * The frame mirrors: in an RTL document the navigation rail is on the right of the content,
 * which is a layout fact the component tests cannot see.
 */
export async function expectMirroredFrame(page: Page, direction: 'ltr' | 'rtl'): Promise<void> {
  const navigation = page.locator('.MuiDrawer-paper').first();
  const content = page.locator('#main-content');
  const navigationBox = await navigation.boundingBox();
  const contentBox = await content.boundingBox();

  expect(navigationBox).not.toBeNull();
  expect(contentBox).not.toBeNull();
  if (!navigationBox || !contentBox) {
    return;
  }

  if (direction === 'rtl') {
    expect(navigationBox.x).toBeGreaterThan(contentBox.x);
  } else {
    expect(navigationBox.x).toBeLessThan(contentBox.x);
  }
}

/** A catalog key is never user-visible; if one leaks, the screen shows an identifier. */
const CATALOG_KEY =
  /\b(?:a11y|auth|common|enums|errors|invitations|members|tickets|workspaces)\.[a-zA-Z0-9_.]+/;

export async function expectNoRawCatalogKeys(page: Page): Promise<void> {
  const text = await page.locator('body').innerText();
  const leaked = text.match(new RegExp(CATALOG_KEY, 'g')) ?? [];
  expect(leaked, `Catalog keys rendered as text: ${leaked.join(', ')}`).toEqual([]);
}
