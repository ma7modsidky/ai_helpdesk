import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

import { request } from '@playwright/test';

/**
 * Seed the backend through its own API.
 *
 * The end-to-end job needs a database with a workspace in it (12_CI_CD §pull request
 * pipeline, step 8), and this creates that state with the public contract only: no fixture
 * file, no shell command against the database, no shared environment. It is idempotent, so
 * a second run reuses what the first one made, and everything it writes is fictional
 * (FR-053). The journey itself creates its own account and workspace; this seed exists so
 * that at least one workspace with tickets is already there when the suite starts, which is
 * what `seeded.spec.ts` reads.
 */

export interface SeedState {
  readonly apiOrigin: string;
  readonly ownerEmail: string;
  readonly ownerPassword: string;
  readonly workspaceId: string;
  readonly workspaceName: string;
  /** The three seeded subjects, in creation order. */
  readonly ticketSubjects: readonly [string, string, string];
}

export const SEED_OWNER = {
  email: 'e2e.seed.owner@example.com',
  password: 'e2e-seed-password-1',
};

export const SEED_WORKSPACE_NAME = 'E2E Seed Workspace';

export const SEED_TICKETS = [
  {
    subject: 'Charged twice for the same month',
    description: 'My statement shows two charges for March.',
    requester_email: 'seed.customer.one@example.com',
    requester_name: 'Seed Customer One',
    priority: 'urgent',
  },
  {
    subject: 'Cannot download the invoice',
    description: 'The download button closes the page.',
    requester_email: 'seed.customer.two@example.com',
    priority: 'normal',
  },
  {
    subject: 'Password reset link expired',
    description: 'The link in the email had already expired when I opened it.',
    requester_email: 'seed.customer.three@example.com',
    priority: 'low',
  },
] as const;

interface CsrfPayload {
  readonly csrf_token?: unknown;
}

interface Paginated<T> {
  readonly count: number;
  readonly results: readonly T[];
}

interface WorkspaceRow {
  readonly id: string;
  readonly name: string;
}

interface MemberRow {
  readonly id: string;
  readonly user_id: string;
  readonly email: string;
}

interface TicketRow {
  readonly id: string;
  readonly status: string;
}

/** Poll readiness until the API answers, so a slow start is a wait rather than a failure. */
export async function waitForApi(apiOrigin: string, timeoutMs = 90_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  const api = await request.newContext({ baseURL: apiOrigin });

  try {
    while (Date.now() < deadline) {
      try {
        const response = await api.get('/health/ready/', { timeout: 5_000 });
        if (response.ok()) {
          return;
        }
      } catch {
        // Not up yet; the loop retries until the deadline.
      }
      await new Promise((resolve) => setTimeout(resolve, 1_000));
    }
  } finally {
    await api.dispose();
  }

  throw new Error(
    `The API at ${apiOrigin} did not become ready. Start the backend (manage.py runserver) before running the journey.`,
  );
}

function readCsrfToken(payload: unknown): string {
  const token = (payload as CsrfPayload | null)?.csrf_token;
  if (typeof token !== 'string' || token.length === 0) {
    throw new Error('The CSRF endpoint did not return a token.');
  }
  return token;
}

/** Seed the demo workspace, its members, and its tickets. Safe to run repeatedly. */
export async function seedBackend(apiOrigin: string): Promise<SeedState> {
  const api = await request.newContext({ baseURL: apiOrigin });
  const jsonHeaders = (token: string) => ({
    'X-CSRFToken': token,
    'Content-Type': 'application/json',
  });

  try {
    let token = readCsrfToken(await (await api.get('/api/v1/auth/csrf/')).json());

    const registered = await api.post('/api/v1/auth/register/', {
      data: { email: SEED_OWNER.email, password: SEED_OWNER.password },
      headers: jsonHeaders(token),
    });

    if (registered.ok()) {
      const body = (await registered.json()) as CsrfPayload;
      token = typeof body.csrf_token === 'string' ? body.csrf_token : token;
    } else {
      // A previous run created the account, which is the normal case for a local rerun.
      const signedIn = await api.post('/api/v1/auth/login/', {
        data: { email: SEED_OWNER.email, password: SEED_OWNER.password },
        headers: jsonHeaders(token),
      });
      if (!signedIn.ok()) {
        throw new Error(
          `The seed account could not be created or signed in (${signedIn.status()} ${await signedIn.text()}).`,
        );
      }
      const body = (await signedIn.json()) as CsrfPayload;
      token = typeof body.csrf_token === 'string' ? body.csrf_token : token;
    }

    const workspaces = (await (
      await api.get('/api/v1/workspaces/?page_size=100')
    ).json()) as Paginated<WorkspaceRow>;
    let workspace = workspaces.results.find((entry) => entry.name === SEED_WORKSPACE_NAME);

    if (!workspace) {
      const created = await api.post('/api/v1/workspaces/', {
        data: { name: SEED_WORKSPACE_NAME, slug: 'e2e-seed-workspace', timezone: 'UTC' },
        headers: jsonHeaders(token),
      });
      if (!created.ok()) {
        throw new Error(
          `The seed workspace was not created (${created.status()} ${await created.text()}).`,
        );
      }
      workspace = (await created.json()) as WorkspaceRow;
    }

    const members = (await (
      await api.get(`/api/v1/workspaces/${workspace.id}/members/?page_size=100`)
    ).json()) as Paginated<MemberRow>;
    const owner = members.results.find((entry) => entry.email === SEED_OWNER.email);

    const tickets = (await (
      await api.get(`/api/v1/workspaces/${workspace.id}/tickets/?page_size=100`)
    ).json()) as Paginated<TicketRow>;

    if (tickets.count === 0) {
      const created: string[] = [];
      for (const [index, seed] of SEED_TICKETS.entries()) {
        const response = await api.post(`/api/v1/workspaces/${workspace.id}/tickets/`, {
          data: seed,
          headers: jsonHeaders(token),
        });
        if (!response.ok()) {
          throw new Error(
            `A seed ticket was not created (${response.status()} ${await response.text()}).`,
          );
        }
        const ticket = (await response.json()) as TicketRow;
        created.push(ticket.id);

        // One ticket is already being worked on, one is resolved, and one carries a public
        // reply, so the inbox shows a queue rather than three identical rows.
        if (index === 1) {
          await api.post(`/api/v1/workspaces/${workspace.id}/tickets/${ticket.id}/transition/`, {
            data: { status: 'in_progress' },
            headers: jsonHeaders(token),
          });
          if (owner) {
            await api.post(`/api/v1/workspaces/${workspace.id}/tickets/${ticket.id}/assign/`, {
              data: { assignee_id: owner.user_id },
              headers: jsonHeaders(token),
            });
          }
        }
        if (index === 2) {
          await api.post(`/api/v1/workspaces/${workspace.id}/tickets/${ticket.id}/messages/`, {
            data: {
              body: 'We have sent a fresh reset link to the address on the account.',
              visibility: 'public_reply',
            },
            headers: jsonHeaders(token),
          });
          await api.post(`/api/v1/workspaces/${workspace.id}/tickets/${ticket.id}/transition/`, {
            data: { status: 'resolved' },
            headers: jsonHeaders(token),
          });
        }
      }
    }

    return {
      apiOrigin,
      ownerEmail: SEED_OWNER.email,
      ownerPassword: SEED_OWNER.password,
      workspaceId: workspace.id,
      workspaceName: workspace.name,
      ticketSubjects: [SEED_TICKETS[0].subject, SEED_TICKETS[1].subject, SEED_TICKETS[2].subject],
    };
  } finally {
    await api.dispose();
  }
}

/** Where the seeded identifiers are recorded for the specs, next to this module. */
export const SEED_STATE_FILE = fileURLToPath(new URL('.seed-state.json', import.meta.url));

/** Seed and record where the seeded data lives, for the specs to read. */
export async function writeSeedState(state: SeedState): Promise<void> {
  await writeFile(SEED_STATE_FILE, `${JSON.stringify(state, null, 2)}\n`, 'utf8');
}

export async function readSeedState(): Promise<SeedState> {
  return JSON.parse(await readFile(SEED_STATE_FILE, 'utf8')) as SeedState;
}
