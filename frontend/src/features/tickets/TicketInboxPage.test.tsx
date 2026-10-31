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

import { TicketInboxPage } from './TicketInboxPage';

const mockedRequest = vi.mocked(apiRequest as unknown as (path: string) => Promise<unknown>);

const TICKET = {
  id: 't1',
  subject: 'Duplicate subscription charge',
  description: 'I see two charges.',
  status: 'open',
  priority: 'urgent',
  category: '',
  requester_email: 'customer@example.com',
  requester_name: 'Sam Customer',
  requester_user_id: null,
  assignee_id: null,
  version: 1,
  first_response_due_at: null,
  first_responded_at: null,
  resolved_at: null,
  created_at: '2026-03-01T08:00:00Z',
  updated_at: '2026-03-02T08:00:00Z',
};

function renderInbox(locale: 'en' | 'ar' = 'en') {
  return renderWithProviders(<TicketInboxPage />, {
    locale,
    route: '/app/w1/inbox',
    path: '/app/:workspaceId/inbox',
  });
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('TicketInboxPage', () => {
  it('renders the queue with status and priority as labelled chips', async () => {
    mockedRequest.mockResolvedValue({ count: 1, next: null, previous: null, results: [TICKET] });

    renderInbox();

    expect(await screen.findByText('Duplicate subscription charge')).toBeInTheDocument();
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText('Urgent')).toBeInTheDocument();
    expect(screen.getByText('customer@example.com')).toBeInTheDocument();
    expect(screen.getByText('1 ticket')).toBeInTheDocument();
    // The subject is the way into the ticket, and it is a real link so it is reachable
    // with the keyboard and shows its destination.
    expect(screen.getByRole('link', { name: 'Duplicate subscription charge' })).toHaveAttribute(
      'href',
      '/app/w1/tickets/t1',
    );
    await expectNoAxeViolations();
  });

  it('asks the server for the workspace, the default ordering, and the first page', async () => {
    mockedRequest.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });

    renderInbox();

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/w1/tickets/?ordering=-updated_at&page=1&page_size=25',
        expect.anything(),
      );
    });
  });

  it('sends a filter to the server rather than filtering the loaded page', async () => {
    mockedRequest.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });

    renderInbox();
    await screen.findByText('No tickets yet');

    await userEvent.click(screen.getByLabelText('Status'));
    await userEvent.click(await screen.findByRole('option', { name: 'Waiting on customer' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/w1/tickets/?status=waiting_on_customer&ordering=-updated_at&page=1&page_size=25',
        expect.anything(),
      );
    });
  });

  it('distinguishes an empty workspace from an empty filter result', async () => {
    mockedRequest.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });

    renderInbox();
    expect(await screen.findByText('No tickets yet')).toBeInTheDocument();
    expect(screen.queryByText('No tickets match these filters')).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('Priority'));
    await userEvent.click(await screen.findByRole('option', { name: 'Urgent' }));

    expect(await screen.findByText('No tickets match these filters')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });

  it('clears every filter from the filtered empty state', async () => {
    mockedRequest.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });

    renderInbox();
    await screen.findByText('No tickets yet');
    await userEvent.click(screen.getByLabelText('Status'));
    await userEvent.click(await screen.findByRole('option', { name: 'Open' }));

    await userEvent.click(await screen.findByRole('button', { name: 'Clear filters' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenLastCalledWith(
        '/workspaces/w1/tickets/?ordering=-updated_at&page=1&page_size=25',
        expect.anything(),
      );
    });
  });

  it('offers a retry when the queue cannot be loaded', async () => {
    mockedRequest.mockRejectedValue(
      new ApiError({ status: 403, code: 'permission_denied', message: 'Denied.' }),
    );

    renderInbox();

    expect(await screen.findByRole('alert')).toHaveTextContent(/role does not allow/i);
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('creates a ticket and opens it', async () => {
    mockedRequest.mockImplementation((_path: string, options?: { method?: string }) =>
      options?.method === 'POST'
        ? Promise.resolve(TICKET)
        : Promise.resolve({ count: 0, next: null, previous: null, results: [] }),
    );

    renderRoutes(
      <Routes>
        <Route path="/app/:workspaceId/inbox" element={<TicketInboxPage />} />
        <Route path="/app/:workspaceId/tickets/:ticketId" element={<p>ticket detail</p>} />
      </Routes>,
      { route: '/app/w1/inbox' },
    );

    await userEvent.click(await screen.findByRole('button', { name: 'New ticket' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/^Subject/), 'Missing invoice');
    await userEvent.type(
      within(dialog).getByLabelText(/^Description/),
      'The March invoice is missing.',
    );
    await userEvent.type(within(dialog).getByLabelText(/^Requester email/), 'customer@example.com');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/w1/tickets/',
        expect.objectContaining({
          method: 'POST',
          // `objectContaining` is untyped, so the shape is asserted explicitly.
          body: expect.objectContaining({
            subject: 'Missing invoice',
            description: 'The March invoice is missing.',
            requester_email: 'customer@example.com',
            priority: 'normal',
          }) as Record<string, unknown>,
        }),
      );
    });
    // Creating lands on the ticket, so the next action is writing to the requester.
    expect(await screen.findByText('ticket detail')).toBeInTheDocument();
  });

  it('renders the Arabic queue with translated labels', async () => {
    mockedRequest.mockResolvedValue({ count: 1, next: null, previous: null, results: [TICKET] });

    renderInbox('ar');

    // Await a data-dependent element first: the page title renders before the queue does.
    expect(await screen.findByText('مفتوحة')).toBeInTheDocument();
    expect(screen.getByText('عاجلة')).toBeInTheDocument();
    expect(screen.getByText('التذاكر')).toBeInTheDocument();
    expect(screen.getByText('تذكرة واحدة')).toBeInTheDocument();
  });
});
