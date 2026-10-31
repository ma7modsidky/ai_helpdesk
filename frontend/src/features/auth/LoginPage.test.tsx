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

import { LoginPage } from './LoginPage';

const mockedRequest = vi.mocked(apiRequest as unknown as (path: string) => Promise<unknown>);

const USER = { id: 'u1', email: 'agent@example.com', is_staff: false };

function unauthenticated(): ApiError {
  return new ApiError({ status: 401, code: 'not_authenticated', message: 'No session.' });
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('LoginPage', () => {
  it('renders labelled fields and passes the accessibility check', async () => {
    mockedRequest.mockRejectedValue(unauthenticated());

    renderWithProviders(<LoginPage />, { route: '/login' });

    expect(await screen.findByLabelText(/^Email/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    await expectNoAxeViolations();
  });

  it('shows a form-level message when the credentials are refused', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        throw unauthenticated();
      }
      throw new ApiError({
        status: 401,
        code: 'authentication_failed',
        message: 'Sign-in failed.',
      });
    });

    renderWithProviders(<LoginPage />, { route: '/login' });
    await userEvent.type(await screen.findByLabelText(/^Email/), 'agent@example.com');
    await userEvent.type(screen.getByLabelText(/^Password/), 'wrong-password');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/session has ended/i);
  });

  it('places server field errors on the matching control', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        throw unauthenticated();
      }
      throw new ApiError({
        status: 400,
        code: 'validation_error',
        message: 'The request was invalid.',
        details: { email: ['Enter a valid email address.'] },
      });
    });

    renderWithProviders(<LoginPage />, { route: '/login' });
    await userEvent.type(await screen.findByLabelText(/^Email/), 'not-an-email');
    await userEvent.type(screen.getByLabelText(/^Password/), 'secret-value');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument();
    expect(screen.getByLabelText(/^Email/)).toHaveAttribute('aria-invalid', 'true');
  });

  it('sends the credentials as JSON through the shared client', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        throw unauthenticated();
      }
      return Promise.resolve({ user: USER, csrf_token: 'token-2' });
    });

    renderWithProviders(<LoginPage />, { route: '/login' });
    await userEvent.type(await screen.findByLabelText(/^Email/), 'agent@example.com');
    await userEvent.type(screen.getByLabelText(/^Password/), 'correct-horse');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/auth/login/',
        expect.objectContaining({
          method: 'POST',
          body: { email: 'agent@example.com', password: 'correct-horse' },
        }),
      );
    });
  });

  it('rejects an off-origin next parameter and lands on the workspace picker', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        throw unauthenticated();
      }
      return Promise.resolve({ user: USER, csrf_token: 'token-3' });
    });

    renderRoutes(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/app/workspaces" element={<p>workspace picker</p>} />
      </Routes>,
      { route: '/login?next=https%3A%2F%2Fevil.example%2Fsteal' },
    );

    await userEvent.type(await screen.findByLabelText(/^Email/), 'agent@example.com');
    await userEvent.type(screen.getByLabelText(/^Password/), 'correct-horse');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('workspace picker')).toBeInTheDocument();
  });

  it('returns the visitor to the attempted path after signing in', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        throw unauthenticated();
      }
      return Promise.resolve({ user: USER, csrf_token: 'token-4' });
    });

    renderRoutes(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/app/:workspaceId/inbox" element={<p>inbox for the workspace</p>} />
      </Routes>,
      { route: `/login?next=${encodeURIComponent('/app/w1/inbox')}` },
    );

    await userEvent.type(await screen.findByLabelText(/^Email/), 'agent@example.com');
    await userEvent.type(screen.getByLabelText(/^Password/), 'correct-horse');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('inbox for the workspace')).toBeInTheDocument();
  });
});
