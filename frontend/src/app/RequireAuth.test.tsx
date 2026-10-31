import { act, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api/client', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiRequest: vi.fn(),
}));

import { LoginPage } from '@/features/auth/LoginPage';
import { apiRequest } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';
import { queryKeys } from '@/lib/api/queryKeys';
import { renderRoutes } from '@/test/renderWithProviders';

import { RequireAuth } from './RequireAuth';

const mockedRequest = vi.mocked(apiRequest as unknown as (path: string) => Promise<unknown>);

const USER = { id: 'u1', email: 'agent@example.com', is_staff: false };

function unauthenticated(): ApiError {
  return new ApiError({ status: 401, code: 'not_authenticated', message: 'No session.' });
}

/** The guard plus the screen it redirects to, wired through the real routes. */
function renderGuard() {
  return renderRoutes(
    <Routes>
      <Route
        path="/app/workspaces"
        element={
          <RequireAuth>
            <p>protected screen</p>
          </RequireAuth>
        }
      />
      <Route path="/login" element={<LoginPage />} />
    </Routes>,
    { route: '/app/workspaces' },
  );
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('RequireAuth', () => {
  it('renders the guarded screen once the session resolves', async () => {
    mockedRequest.mockResolvedValue(USER);

    renderGuard();

    expect(await screen.findByText('protected screen')).toBeInTheDocument();
  });

  it('never renders the guarded screen before the session answers', async () => {
    mockedRequest.mockImplementation(() => {
      throw unauthenticated();
    });

    renderGuard();

    // A deep link reloaded by a signed-out visitor must not flash the protected tree.
    expect(screen.queryByText('protected screen')).not.toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('sends a first-time visitor to a plain sign-in form', async () => {
    mockedRequest.mockImplementation(() => {
      throw unauthenticated();
    });

    renderGuard();

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.queryByText(/sign in again to continue/i)).not.toBeInTheDocument();
  });

  it('explains an expiry when a session is lost after it was established', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        return Promise.resolve(USER);
      }
      throw unauthenticated();
    });

    const { queryClient } = renderGuard();
    expect(await screen.findByText('protected screen')).toBeInTheDocument();

    // Exactly what the shared client does when any request answers 401: the session entry
    // becomes null, and the guard has to remember that there was one.
    act(() => {
      queryClient.setQueryData(queryKeys.session, null);
    });

    expect(await screen.findByText(/sign in again to continue/i)).toBeInTheDocument();
  });
});
