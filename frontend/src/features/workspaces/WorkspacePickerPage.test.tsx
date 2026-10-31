import { screen, waitFor, within } from '@testing-library/react';
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

import { WorkspacePickerPage } from './WorkspacePickerPage';

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

function page(results: readonly unknown[], count = results.length) {
  return { count, next: null, previous: null, results };
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('WorkspacePickerPage', () => {
  it('lists the workspaces the account belongs to', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        return Promise.resolve(USER);
      }
      return Promise.resolve(
        page([WORKSPACE, { ...WORKSPACE, id: 'w2', name: 'Billing', slug: 'billing' }]),
      );
    });

    renderWithProviders(<WorkspacePickerPage />, { route: '/app/workspaces' });

    expect(await screen.findByText('Acme Support')).toBeInTheDocument();
    expect(screen.getByText('Billing')).toBeInTheDocument();
    expect(screen.getByText(/agent@example\.com/)).toBeInTheDocument();
    await expectNoAxeViolations();
  });

  it('explains both ways into a workspace when the account has none', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        return Promise.resolve(USER);
      }
      return Promise.resolve(page([]));
    });

    renderWithProviders(<WorkspacePickerPage />, { route: '/app/workspaces' });

    expect(await screen.findByText('No workspace yet')).toBeInTheDocument();
    expect(screen.getByText(/invitation grants access/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create workspace/i })).toBeInTheDocument();
  });

  it('offers a retry instead of an empty list when the request fails', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        return Promise.resolve(USER);
      }
      throw new ApiError({
        status: 500,
        code: 'internal_error',
        message: 'An unexpected error occurred.',
        requestId: 'req-42',
      });
    });

    renderWithProviders(<WorkspacePickerPage />, { route: '/app/workspaces' });

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/Request ID: req-42/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('derives the slug from the name and creates the workspace', async () => {
    mockedRequest.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/auth/me/') {
        return Promise.resolve(USER);
      }
      if (options?.method === 'POST') {
        return Promise.resolve(WORKSPACE);
      }
      return Promise.resolve(page([]));
    });

    renderRoutes(
      <Routes>
        <Route path="/app/workspaces" element={<WorkspacePickerPage />} />
        <Route path="/app/:workspaceId/inbox" element={<p>inbox for the workspace</p>} />
      </Routes>,
      { route: '/app/workspaces' },
    );

    await userEvent.click(await screen.findByRole('button', { name: /create workspace/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/^Name/), 'Acme Support');

    await waitFor(() => {
      expect(within(dialog).getByLabelText(/^Slug/)).toHaveValue('acme-support');
    });

    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/',
        expect.objectContaining({
          method: 'POST',
          // The browser reports its own timezone, so any string is correct here.
          body: {
            name: 'Acme Support',
            slug: 'acme-support',
            timezone: expect.any(String) as string,
          },
        }),
      );
    });
    expect(await screen.findByText('inbox for the workspace')).toBeInTheDocument();
  });

  it('shows a duplicate slug as a field error from the server', async () => {
    mockedRequest.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/auth/me/') {
        return Promise.resolve(USER);
      }
      if (options?.method === 'POST') {
        throw new ApiError({
          status: 400,
          code: 'validation_error',
          message: 'The request was invalid.',
          details: { slug: ['This slug is already taken.'] },
        });
      }
      return Promise.resolve(page([]));
    });

    renderWithProviders(<WorkspacePickerPage />, { route: '/app/workspaces' });

    await userEvent.click(await screen.findByRole('button', { name: /create workspace/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/^Name/), 'Acme');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('This slug is already taken.')).toBeInTheDocument();
  });
});
