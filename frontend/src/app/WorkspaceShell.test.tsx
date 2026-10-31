import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useParams } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api/client', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';
import { renderRoutes } from '@/test/renderWithProviders';
import { expectNoAxeViolations } from '@/test/axe';

import { WorkspaceShell } from './WorkspaceShell';

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

const OTHER_WORKSPACE = { ...WORKSPACE, id: 'w2', name: 'Billing', slug: 'billing' };

function page(results: readonly unknown[]) {
  return { count: results.length, next: null, previous: null, results };
}

/** Stands in for a workspace screen, so a switch can be observed in the URL. */
function InboxProbe() {
  const { workspaceId = '' } = useParams<{ workspaceId: string }>();
  return <p>inbox for {workspaceId}</p>;
}

function renderShell({ route = `/app/${WORKSPACE.id}/inbox` } = {}) {
  return renderRoutes(
    <Routes>
      <Route path="/app/workspaces" element={<p>workspace picker</p>} />
      <Route path="/login" element={<p>sign-in form</p>} />
      <Route path="/app/:workspaceId" element={<WorkspaceShell />}>
        <Route path="inbox" element={<InboxProbe />} />
      </Route>
    </Routes>,
    { route },
  );
}

/** The session and the workspace list, which every shell test needs. */
function mockSignedIn(workspaces: readonly unknown[] = [WORKSPACE, OTHER_WORKSPACE]) {
  mockedRequest.mockImplementation((path: string) => {
    if (path === '/auth/me/') {
      return Promise.resolve(USER);
    }
    if (path.startsWith('/workspaces/')) {
      return Promise.resolve(page(workspaces));
    }
    if (path === '/auth/logout/') {
      return Promise.resolve(undefined);
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('WorkspaceShell', () => {
  it('names the current workspace and the navigation, and passes the accessibility check', async () => {
    mockSignedIn();

    renderShell();

    expect(await screen.findByText('Acme Support')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Your workspaces' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Tickets' })).toHaveAttribute('href', '/app/w1/inbox');
    expect(await screen.findByText('inbox for w1')).toBeInTheDocument();
    await expectNoAxeViolations();
  });

  it('does not render the frame before the workspace list resolves', async () => {
    let resolveWorkspaces: (value: unknown) => void = () => undefined;
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        return Promise.resolve(USER);
      }
      return new Promise((resolve) => {
        resolveWorkspaces = resolve;
      });
    });

    renderShell();

    expect(await screen.findByRole('status')).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Your workspaces' })).not.toBeInTheDocument();

    resolveWorkspaces(page([WORKSPACE]));

    expect(await screen.findByText('inbox for w1')).toBeInTheDocument();
  });

  it('explains a workspace the account cannot see instead of rendering an empty frame', async () => {
    mockSignedIn([OTHER_WORKSPACE]);

    renderShell({ route: '/app/w1/inbox' });

    expect(
      await screen.findByText('It may have been archived, or your access may have been removed.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Your workspaces' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Back to your workspaces' }));

    expect(await screen.findByText('workspace picker')).toBeInTheDocument();
  });

  it('switches to another workspace from the switcher', async () => {
    mockSignedIn();

    renderShell();
    expect(await screen.findByText('inbox for w1')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Acme Support' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Billing' }));

    expect(await screen.findByText('inbox for w2')).toBeInTheDocument();
  });

  it('signs out through the API and returns to the sign-in form', async () => {
    mockSignedIn();

    renderShell();
    await screen.findByText('inbox for w1');

    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Sign out' }));

    expect(await screen.findByText('sign-in form')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/auth/logout/',
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('offers a retry when the workspace list fails, and recovers on the second attempt', async () => {
    let attempts = 0;
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        return Promise.resolve(USER);
      }
      attempts += 1;
      if (attempts === 1) {
        throw new ApiError({
          status: 500,
          code: 'internal_error',
          message: 'An unexpected error occurred.',
          requestId: 'req-7',
        });
      }
      return Promise.resolve(page([WORKSPACE]));
    });

    renderShell();

    const panel = await screen.findByRole('alert');
    expect(panel).toHaveTextContent('Request ID: req-7');
    await userEvent.click(within(panel).getByRole('button', { name: 'Try again' }));

    expect(await screen.findByText('inbox for w1')).toBeInTheDocument();
  });
});
