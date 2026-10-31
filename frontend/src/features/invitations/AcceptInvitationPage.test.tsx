import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api/client', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';
import { renderRoutes, renderWithProviders } from '@/test/renderWithProviders';
import { expectNoAxeViolations } from '@/test/axe';

import { AcceptInvitationPage } from './AcceptInvitationPage';

const mockedRequest = vi.mocked(apiRequest as unknown as (path: string) => Promise<unknown>);

const USER = { id: 'u1', email: 'invitee@example.com', is_staff: false };

const PREVIEW = {
  workspace_name: 'Acme Support',
  role: 'agent',
  status: 'pending',
  expires_at: '2026-11-03T10:00:00Z',
};

function unauthenticated(): ApiError {
  return new ApiError({ status: 401, code: 'not_authenticated', message: 'No session.' });
}

/** Wire the session and the invitation preview, leaving the accept call to the test. */
function mockPreview(
  preview: unknown,
  { user = null, accept }: { user?: unknown; accept?: () => Promise<unknown> } = {},
) {
  mockedRequest.mockImplementation((path: string) => {
    if (path === '/auth/me/') {
      if (user) {
        return Promise.resolve(user);
      }
      throw unauthenticated();
    }
    if (path === '/invitations/preview/') {
      return Promise.resolve(preview);
    }
    if (path === '/invitations/accept/' && accept) {
      return accept();
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('AcceptInvitationPage', () => {
  it('shows the workspace, the role, and the sign-in requirement before acting', async () => {
    mockPreview(PREVIEW);

    renderWithProviders(<AcceptInvitationPage />, {
      route: '/invite/token-1',
      path: '/invite/:token',
    });

    expect(await screen.findByText(/invited to join Acme Support/i)).toBeInTheDocument();
    expect(screen.getAllByText('Agent').length).toBeGreaterThan(0);
    expect(screen.getByText(/sign in or create an account/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Accept invitation' })).not.toBeInTheDocument();
    await expectNoAxeViolations();
  });

  it('reports an unknown token honestly instead of offering acceptance', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        throw unauthenticated();
      }
      throw new ApiError({
        status: 404,
        code: 'not_found',
        message: 'The requested resource was not found.',
      });
    });

    renderWithProviders(<AcceptInvitationPage />, {
      route: '/invite/gone',
      path: '/invite/:token',
    });

    expect(await screen.findByText(/link is not valid/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Accept invitation' })).not.toBeInTheDocument();
  });

  it.each([
    ['expired', /this invitation expired/i],
    ['revoked', /revoked/i],
    ['accepted', /already accepted/i],
  ])('explains a %s invitation and withdraws the accept action', async (state, expected) => {
    mockPreview({ ...PREVIEW, status: state }, { user: USER });

    renderWithProviders(<AcceptInvitationPage />, {
      route: '/invite/token-1',
      path: '/invite/:token',
    });

    expect(await screen.findByText(expected)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Accept invitation' })).not.toBeInTheDocument();
  });

  it('accepts a pending invitation and opens the workspace inbox', async () => {
    mockPreview(PREVIEW, {
      user: USER,
      accept: () =>
        Promise.resolve({
          workspace: {
            id: 'w1',
            name: 'Acme Support',
            slug: 'acme-support',
            timezone: 'UTC',
            status: 'active',
            created_at: '2026-01-02T10:00:00Z',
          },
          membership: {
            id: 'm1',
            user_id: 'u1',
            email: 'invitee@example.com',
            role: 'agent',
            status: 'active',
            created_at: '2026-01-02T10:00:00Z',
          },
        }),
    });

    renderRoutes(
      <Routes>
        <Route path="/invite/:token" element={<AcceptInvitationPage />} />
        <Route path="/app/:workspaceId/inbox" element={<p>workspace inbox</p>} />
      </Routes>,
      { route: '/invite/token-1' },
    );

    await userEvent.click(await screen.findByRole('button', { name: 'Accept invitation' }));

    expect(await screen.findByText('workspace inbox')).toBeInTheDocument();
  });

  it('explains a mismatched account when acceptance is refused', async () => {
    mockPreview(PREVIEW, {
      user: USER,
      accept: () =>
        Promise.reject(
          new ApiError({ status: 403, code: 'permission_denied', message: 'Not your invitation.' }),
        ),
    });

    renderWithProviders(<AcceptInvitationPage />, {
      route: '/invite/token-1',
      path: '/invite/:token',
    });

    await userEvent.click(await screen.findByRole('button', { name: 'Accept invitation' }));

    await waitFor(() => {
      expect(
        screen.getByText(/invitee@example.com, which is not the invited address/i),
      ).toBeInTheDocument();
    });
    // The switch-account control is a link, because it navigates rather than acting.
    expect(screen.getByRole('link', { name: 'Sign in with another address' })).toBeInTheDocument();
  });

  it('reports an invitation that expired between loading and accepting', async () => {
    mockPreview(PREVIEW, {
      user: USER,
      accept: () =>
        Promise.reject(
          new ApiError({
            status: 409,
            code: 'invitation_expired',
            message: 'This invitation has expired.',
          }),
        ),
    });

    renderWithProviders(<AcceptInvitationPage />, {
      route: '/invite/token-1',
      path: '/invite/:token',
    });

    await userEvent.click(await screen.findByRole('button', { name: 'Accept invitation' }));

    expect(await screen.findByText(/this invitation expired/i)).toBeInTheDocument();
  });
});
