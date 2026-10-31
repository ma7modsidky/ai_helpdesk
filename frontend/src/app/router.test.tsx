import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api/client', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api/client';
import { renderRoutes } from '@/test/renderWithProviders';

import { AppRoutes } from './router';

const mockedRequest = vi.mocked(apiRequest as unknown as (path: string) => Promise<unknown>);

const USER = { id: 'u1', email: 'agent@example.com', is_staff: false };

const WORKSPACE = {
  id: 'w1',
  name: 'Acme Support',
  slug: 'acme-support',
  timezone: 'Africa/Cairo',
  status: 'active',
  created_at: '2026-01-02T10:00:00Z',
};

function page(results: readonly unknown[]) {
  return { count: results.length, next: null, previous: null, results };
}

/** A signed-in account with one workspace and an empty queue. */
function mockSignedIn() {
  mockedRequest.mockImplementation((path: string) => {
    if (path === '/auth/me/') {
      return Promise.resolve(USER);
    }
    if (path.startsWith('/workspaces/') && path.includes('/tickets/')) {
      return Promise.resolve(page([]));
    }
    if (path.startsWith('/workspaces/')) {
      return Promise.resolve(page([WORKSPACE]));
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

/**
 * Lazy routes load their chunk on demand, which under a full parallel test run can take
 * longer than the default one-second wait. The wait is longer; the assertion is not weaker.
 */
const LAZY_ROUTE_TIMEOUT = { timeout: 5000 };

function renderApp(route: string) {
  return renderRoutes(<AppRoutes />, { route });
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('AppRoutes', () => {
  it('sends the root path to the workspace picker', async () => {
    mockSignedIn();

    renderApp('/');

    expect(
      await screen.findByRole('heading', { name: 'Your workspaces' }, LAZY_ROUTE_TIMEOUT),
    ).toBeInTheDocument();
    expect(await screen.findByText('Acme Support')).toBeInTheDocument();
  });

  it('opens the workspace inbox for a workspace the account belongs to', async () => {
    mockSignedIn();

    renderApp('/app/w1');

    // `/app/:workspaceId` is a hint: the index route resolves to the default screen, which
    // is loaded on demand.
    expect(
      await screen.findByText('No tickets yet', undefined, LAZY_ROUTE_TIMEOUT),
    ).toBeInTheDocument();
  });

  it('explains an unknown URL and offers the way back', async () => {
    mockSignedIn();

    renderApp('/nonsense/path');

    expect(
      await screen.findByText('We could not find what you were looking for.'),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Back to your workspaces' }));

    expect(await screen.findByRole('heading', { name: 'Your workspaces' })).toBeInTheDocument();
  });
});
