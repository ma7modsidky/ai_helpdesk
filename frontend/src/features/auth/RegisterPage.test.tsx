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

import { RegisterPage } from './RegisterPage';

const mockedRequest = vi.mocked(apiRequest as unknown as (path: string) => Promise<unknown>);

const USER = { id: 'u1', email: 'new@example.com', is_staff: false };

function unauthenticated(): ApiError {
  return new ApiError({ status: 401, code: 'not_authenticated', message: 'No session.' });
}

/** A signed-out visitor, with the registration call left to the test. */
function mockSignedOut(response: () => Promise<unknown>) {
  mockedRequest.mockImplementation((path: string) => {
    if (path === '/auth/me/') {
      throw unauthenticated();
    }
    if (path === '/auth/register/') {
      return response();
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

function renderRegister() {
  return renderRoutes(
    <Routes>
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/app/workspaces" element={<p>workspace picker</p>} />
    </Routes>,
    { route: '/register' },
  );
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('RegisterPage', () => {
  it('renders labelled fields with the password rule stated, and passes the accessibility check', async () => {
    mockSignedOut(() => Promise.resolve({ user: USER, csrf_token: 'token-1' }));

    renderWithProviders(<RegisterPage />, { route: '/register' });

    expect(await screen.findByLabelText(/^Email/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password/)).toBeInTheDocument();
    expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument();
    await expectNoAxeViolations();
  });

  it('creates the account and lands on the workspace picker', async () => {
    mockSignedOut(() => Promise.resolve({ user: USER, csrf_token: 'token-2' }));

    renderRegister();

    await userEvent.type(await screen.findByLabelText(/^Email/), 'new@example.com');
    await userEvent.type(screen.getByLabelText(/^Password/), 'correct-horse');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/auth/register/',
        expect.objectContaining({
          method: 'POST',
          body: { email: 'new@example.com', password: 'correct-horse' },
        }),
      );
    });
    expect(await screen.findByText('workspace picker')).toBeInTheDocument();
  });

  it('places the server password rule on the password control rather than guessing it', async () => {
    mockSignedOut(() =>
      Promise.reject(
        new ApiError({
          status: 400,
          code: 'validation_error',
          message: 'The request was invalid.',
          details: { password: ['This password is too common.'] },
        }),
      ),
    );

    renderRegister();

    await userEvent.type(await screen.findByLabelText(/^Email/), 'new@example.com');
    await userEvent.type(screen.getByLabelText(/^Password/), 'password');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));

    expect(await screen.findByText('This password is too common.')).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password/)).toHaveAttribute('aria-invalid', 'true');
  });

  it('never shows the form to a visitor who already has a session', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        return Promise.resolve(USER);
      }
      throw new Error(`Unexpected request: ${path}`);
    });

    renderRegister();

    expect(await screen.findByText('workspace picker')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create account' })).not.toBeInTheDocument();
  });
});
