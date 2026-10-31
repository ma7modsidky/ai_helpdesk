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
import { renderRoutes } from '@/test/renderWithProviders';
import { expectNoAxeViolations } from '@/test/axe';

import { MembersPage } from './MembersPage';

const mockedRequest = vi.mocked(
  apiRequest as unknown as (
    path: string,
    options?: { method?: string; body?: unknown },
  ) => Promise<unknown>,
);

const OWNER = { id: 'u1', email: 'owner@example.com', is_staff: false };

const OWNER_ROW = {
  id: 'm-owner',
  user_id: 'u1',
  email: 'owner@example.com',
  role: 'owner',
  status: 'active',
  created_at: '2026-01-02T10:00:00Z',
};

const AGENT_ROW = {
  id: 'm-agent',
  user_id: 'u2',
  email: 'agent@example.com',
  role: 'agent',
  status: 'active',
  created_at: '2026-01-05T10:00:00Z',
};

const EXPIRED_INVITATION = {
  id: 'i1',
  email: 'invitee@example.com',
  role: 'agent',
  status: 'expired',
  expires_at: '2026-02-01T10:00:00Z',
  created_at: '2026-01-20T10:00:00Z',
  invited_by: { user_id: 'u1', email: 'owner@example.com' },
  delivery_status: 'sent',
};

function page(results: readonly unknown[]) {
  return { count: results.length, next: null, previous: null, results };
}

interface MockOptions {
  readonly user?: unknown;
  readonly members?: readonly unknown[];
  readonly invitations?: readonly unknown[];
  readonly onWrite?: (path: string, method: string) => unknown;
}

/** The session, the member list, the invitation list, and a hook for the write routes. */
function mockMembers(options: MockOptions = {}) {
  const { user = OWNER, members = [OWNER_ROW, AGENT_ROW], invitations = [], onWrite } = options;

  mockedRequest.mockImplementation((path: string, requestOptions) => {
    const method = requestOptions?.method ?? 'GET';
    if (path === '/auth/me/') {
      return Promise.resolve(user);
    }
    if (method !== 'GET') {
      if (onWrite) {
        const outcome = onWrite(path, method);
        if (outcome instanceof Error) {
          throw outcome;
        }
        return Promise.resolve(outcome);
      }
      throw new Error(`Unexpected write: ${method} ${path}`);
    }
    if (path.startsWith('/workspaces/w1/members/')) {
      return Promise.resolve(page(members));
    }
    if (path.startsWith('/workspaces/w1/invitations/')) {
      return Promise.resolve(page(invitations));
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

function renderMembers() {
  return renderRoutes(
    <Routes>
      <Route path="/app/:workspaceId/settings/members" element={<MembersPage />} />
    </Routes>,
    { route: '/app/w1/settings/members' },
  );
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('MembersPage', () => {
  it('lists members with their role and status, and passes the accessibility check', async () => {
    mockMembers();

    renderMembers();

    expect(await screen.findByText('agent@example.com')).toBeInTheDocument();
    expect(screen.getByText('owner@example.com')).toBeInTheDocument();
    expect(screen.getByText('Agent')).toBeInTheDocument();
    expect(screen.getAllByText('Active')).toHaveLength(2);
    expect(screen.queryByText('Access withdrawn')).not.toBeInTheDocument();
    await expectNoAxeViolations();
  });

  it('explains the last-owner rule when a demotion is refused, and changes nothing', async () => {
    mockMembers({
      onWrite: () => new ApiError({ status: 409, code: 'conflict', message: 'Last owner.' }),
    });

    renderMembers();

    const roleSelect = await screen.findByLabelText('Role', {
      selector: '#member-role-m-owner',
    });
    await userEvent.click(roleSelect);
    await userEvent.click(await screen.findByRole('option', { name: 'Agent' }));

    expect(await screen.findByText(/must keep at least one active owner/i)).toBeInTheDocument();
    expect(screen.getByText('Owner')).toBeInTheDocument();
  });

  it('offers no membership controls to a role without the capability, and says why', async () => {
    mockMembers({
      user: { id: 'u2', email: 'agent@example.com', is_staff: false },
      members: [OWNER_ROW, AGENT_ROW],
    });

    renderMembers();

    expect(
      await screen.findByText(/you can see the members but not change them/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /invite someone/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /make owner/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Role' })).not.toBeInTheDocument();
  });

  it('shows an expired invitation and reveals the rotated link exactly once on resend', async () => {
    mockMembers({
      invitations: [EXPIRED_INVITATION],
      onWrite: () => ({ ...EXPIRED_INVITATION, status: 'pending', accept_path: '/invite/fresh' }),
    });

    renderMembers();

    expect(await screen.findByText('invitee@example.com')).toBeInTheDocument();
    expect(screen.getByText('Expired')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Resend' }));

    expect(await screen.findByText('/invite/fresh')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Done' }));

    // The token is never rendered again: no read path returns it (ADR-026).
    await waitFor(() => {
      expect(screen.queryByText('/invite/fresh')).not.toBeInTheDocument();
    });
    expect(mockedRequest).toHaveBeenCalledWith(
      '/workspaces/w1/invitations/i1/resend/',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('creates an invitation and shows the accept link with the invited role', async () => {
    mockMembers({
      onWrite: () => ({
        ...EXPIRED_INVITATION,
        id: 'i2',
        status: 'pending',
        accept_path: '/invite/new-token',
      }),
    });

    renderMembers();

    await userEvent.click(await screen.findByRole('button', { name: /invite someone/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/^Email/), 'new@example.com');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create invitation' }));

    expect(await screen.findByText('/invite/new-token')).toBeInTheDocument();
    expect(screen.getByText(/joins as Agent/i)).toBeInTheDocument();
    expect(mockedRequest).toHaveBeenCalledWith(
      '/workspaces/w1/invitations/',
      expect.objectContaining({
        method: 'POST',
        body: { email: 'new@example.com', role: 'agent' },
      }),
    );
  });

  it('confirms an ownership handover and states what happens to the caller', async () => {
    mockMembers({
      onWrite: (path, method) => {
        expect(path).toBe('/workspaces/w1/transfer-ownership/');
        expect(method).toBe('POST');
        return {
          owner: { ...AGENT_ROW, role: 'owner' },
          previous_owner: { ...OWNER_ROW, role: 'admin' },
        };
      },
    });

    renderMembers();

    const rows = await screen.findAllByRole('row');
    const agentRow = rows.find((row) => within(row).queryByText('agent@example.com'));
    expect(agentRow).toBeDefined();
    await userEvent.click(within(agentRow!).getByRole('button', { name: 'Make owner' }));

    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByText(/becomes the owner of this workspace, and you become an admin/i),
    ).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole('button', { name: 'Hand over ownership' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/w1/transfer-ownership/',
        expect.objectContaining({ method: 'POST', body: { membership_id: 'm-agent' } }),
      );
    });
  });
});
