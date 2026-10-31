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

import { TicketDetailPage } from './TicketDetailPage';

const mockedRequest = vi.mocked(
  apiRequest as unknown as (
    path: string,
    options?: { method?: string; body?: unknown },
  ) => Promise<unknown>,
);

const OWNER = { id: 'u1', email: 'owner@example.com', is_staff: false };
const AGENT = { id: 'u2', email: 'agent@example.com', is_staff: false };

const OWNER_ROW = {
  id: 'm1',
  user_id: 'u1',
  email: 'owner@example.com',
  role: 'owner',
  status: 'active',
  created_at: '2026-01-02T10:00:00Z',
};

const AGENT_ROW = {
  id: 'm2',
  user_id: 'u2',
  email: 'agent@example.com',
  role: 'agent',
  status: 'active',
  created_at: '2026-01-05T10:00:00Z',
};

const TICKET = {
  id: 't1',
  subject: 'Duplicate subscription charge',
  description: 'I see two charges for my monthly subscription.',
  status: 'open',
  priority: 'normal',
  category: '',
  requester_email: 'customer@example.com',
  requester_name: 'Sam Customer',
  requester_user_id: null,
  assignee_id: null,
  version: 1,
  first_response_due_at: null,
  first_responded_at: null,
  resolved_at: null,
  created_at: '2026-01-02T10:00:00Z',
  updated_at: '2026-01-02T10:00:00Z',
};

const PUBLIC_REPLY = {
  id: 'msg1',
  body: 'We are looking into this.',
  visibility: 'public_reply',
  author: { user_id: 'u1', email: 'owner@example.com' },
  created_at: '2026-01-02T11:00:00Z',
};

const INTERNAL_NOTE = {
  id: 'msg2',
  body: 'Billing service is known to double-charge on retries.',
  visibility: 'internal_note',
  author: { user_id: 'u1', email: 'owner@example.com' },
  created_at: '2026-01-02T11:30:00Z',
};

const CLASSIFICATION = {
  status: 'succeeded',
  category: 'billing',
  sentiment: 'negative',
  suggested_priority: 'high',
  confidence: 0.82,
  rationale: 'Customer reports a duplicate charge and previous unanswered contacts.',
  provider: 'fake',
  model: 'fake-model-v1',
  created_at: '2026-01-02T09:00:00Z',
};

const DRAFT_WITH_SOURCE = {
  id: 'd1',
  status: 'succeeded',
  draft_text: 'We have refunded the duplicate charge. It should appear within five business days.',
  source_articles: [{ article_id: 'article-1', title: 'Refund policy' }],
  provider: 'fake',
  model: 'fake-model-v1',
  requires_human_approval: true,
  error: null,
  created_at: '2026-01-02T12:00:00Z',
};

function page(results: readonly unknown[]) {
  return { count: results.length, next: null, previous: null, results };
}

interface MockOptions {
  readonly user?: unknown;
  readonly members?: readonly unknown[];
  readonly ticket?: unknown;
  readonly messages?: readonly unknown[];
  readonly ai?: { readonly classification?: unknown; readonly draft?: unknown };
  readonly onWrite?: (path: string, method: string, body: unknown) => unknown;
}

/** The session, the member list, one ticket, its conversation, and a write hook. */
function mockTicket(options: MockOptions = {}) {
  const {
    user = OWNER,
    members = [OWNER_ROW, AGENT_ROW],
    ticket = TICKET,
    messages = [PUBLIC_REPLY, INTERNAL_NOTE],
    ai = { classification: null, draft: null },
    onWrite,
  } = options;

  mockedRequest.mockImplementation((path: string, requestOptions) => {
    const method = requestOptions?.method ?? 'GET';
    if (path === '/auth/me/') {
      return Promise.resolve(user);
    }
    if (method !== 'GET') {
      if (onWrite) {
        const outcome = onWrite(path, method, requestOptions?.body);
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
    if (path === '/workspaces/w1/tickets/t1/') {
      return Promise.resolve(ticket);
    }
    if (path.startsWith('/workspaces/w1/tickets/t1/messages/')) {
      return Promise.resolve(page(messages));
    }
    if (path === '/workspaces/w1/tickets/t1/ai-status/') {
      return Promise.resolve({
        classification: ai.classification ?? null,
        draft: ai.draft ?? null,
      });
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

function renderDetail() {
  return renderRoutes(
    <Routes>
      <Route path="/app/:workspaceId/tickets/:ticketId" element={<TicketDetailPage />} />
      <Route path="/app/:workspaceId/inbox" element={<p>inbox screen</p>} />
    </Routes>,
    { route: '/app/w1/tickets/t1' },
  );
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('TicketDetailPage', () => {
  it('shows the ticket and treats a reply and a note differently, and passes the accessibility check', async () => {
    mockTicket();

    renderDetail();

    expect(
      await screen.findByRole('heading', { name: 'Duplicate subscription charge' }),
    ).toBeInTheDocument();
    expect(screen.getByText('I see two charges for my monthly subscription.')).toBeInTheDocument();
    expect(screen.getByText(/Sam Customer/)).toBeInTheDocument();

    // Both appear twice: as the timeline's treatment of a message and as the composer's
    // mode, which is the point — the label is one vocabulary, not two.
    expect(screen.getAllByText('Public reply').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Internal note').length).toBeGreaterThan(0);
    // The note says who can read it, which is what keeps the distinction unambiguous.
    expect(screen.getAllByText('Only your team can see this.').length).toBeGreaterThan(0);
    await expectNoAxeViolations();
  });

  it('sends a message only after an explicit visibility choice', async () => {
    mockTicket({
      onWrite: () => ({ ...PUBLIC_REPLY, id: 'msg3' }),
    });

    renderDetail();

    const composer = await screen.findByLabelText('Message');
    await userEvent.type(composer, 'We have refunded the duplicate charge.');

    const send = screen.getByRole('button', { name: 'Send' });
    expect(send).toBeDisabled();
    expect(screen.getByText(/choose whether this is a reply/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Public reply' }));
    expect(send).toBeEnabled();
    await userEvent.click(send);

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/w1/tickets/t1/messages/',
        expect.objectContaining({
          method: 'POST',
          body: {
            body: 'We have refunded the duplicate charge.',
            visibility: 'public_reply',
          },
        }),
      );
    });
    // A sent message leaves the composer empty but keeps no mode selected.
    expect(composer).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Public reply' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('edits a field with the version it read', async () => {
    mockTicket({
      onWrite: () => ({ ...TICKET, priority: 'high', version: 2 }),
    });

    renderDetail();

    const priority = await screen.findByLabelText('Priority', { selector: '#ticket-priority' });
    await userEvent.click(priority);
    await userEvent.click(await screen.findByRole('option', { name: 'High' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/w1/tickets/t1/',
        expect.objectContaining({ method: 'PATCH', body: { priority: 'high' } }),
      );
    });
  });

  it('prompts to reload on a stale version and keeps unsent writing', async () => {
    mockTicket({
      onWrite: () =>
        new ApiError({
          status: 409,
          code: 'conflict',
          message: 'The ticket changed.',
          details: { version: 4 },
        }),
    });

    renderDetail();

    const composer = await screen.findByLabelText('Message');
    await userEvent.type(composer, 'Draft I have not sent yet');

    const priority = await screen.findByLabelText('Priority', { selector: '#ticket-priority' });
    await userEvent.click(priority);
    await userEvent.click(await screen.findByRole('option', { name: 'Urgent' }));

    expect(await screen.findByText(/changed since you loaded it/i)).toBeInTheDocument();
    expect(composer).toHaveValue('Draft I have not sent yet');
    // Reload is offered; a silent overwrite never is.
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });

  it('surfaces an illegal transition from the server instead of predicting it', async () => {
    mockTicket({
      onWrite: () =>
        new ApiError({ status: 409, code: 'conflict', message: 'Illegal transition.' }),
    });

    renderDetail();

    const status = await screen.findByLabelText('Status', { selector: '#ticket-status' });
    await userEvent.click(status);
    await userEvent.click(await screen.findByRole('option', { name: 'Closed' }));

    expect(await screen.findByText(/not allowed from the current state/i)).toBeInTheDocument();
  });

  it('limits assignment to what the role may do', async () => {
    mockTicket({
      user: AGENT,
      members: [OWNER_ROW, AGENT_ROW],
      onWrite: () => ({ ...TICKET, assignee_id: 'u2' }),
    });

    renderDetail();

    const assignee = await screen.findByLabelText('Assignee', { selector: '#ticket-assignee' });
    await userEvent.click(assignee);

    // An agent can take a ticket and release it, but not hand it to someone else.
    expect(await screen.findByRole('option', { name: 'agent@example.com' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'owner@example.com' })).not.toBeInTheDocument();
  });

  it('disables the controls and explains why when no role is resolved for this workspace', async () => {
    // The caller is signed in but has no membership row here, so the screen knows of no
    // role to offer controls for.
    mockTicket({ user: OWNER, members: [AGENT_ROW] });

    renderDetail();

    const status = await screen.findByLabelText('Status', { selector: '#ticket-status' });
    const priority = await screen.findByLabelText('Priority', { selector: '#ticket-priority' });

    // The controls are inert — opening one offers nothing to choose — and the screen says
    // why, rather than leaving a reader to guess at a dead control.
    await userEvent.click(status);
    expect(screen.queryByRole('option', { name: 'Closed' })).not.toBeInTheDocument();
    await userEvent.click(priority);
    expect(screen.queryByRole('option', { name: 'Urgent' })).not.toBeInTheDocument();
    expect(screen.getByText(/can read this ticket but not change it/i)).toBeInTheDocument();
  });

  it('links back to the inbox', async () => {
    mockTicket();

    renderDetail();

    await userEvent.click(await screen.findByRole('link', { name: 'Back to the inbox' }));

    expect(await screen.findByText('inbox screen')).toBeInTheDocument();
  });
});

describe('TicketDetailPage AI panel', () => {
  it('shows the draft with its cited sources and sends it only when asked', async () => {
    const writes: { path: string; body: unknown }[] = [];
    mockTicket({
      ai: { draft: DRAFT_WITH_SOURCE },
      onWrite: (path, method, body) => {
        writes.push({ path, body });
        expect(method).toBe('POST');
        return { ...PUBLIC_REPLY, id: 'msg9' };
      },
    });

    renderDetail();

    const editor = await screen.findByLabelText('Draft reply');
    expect(editor).toHaveValue(DRAFT_WITH_SOURCE.draft_text);
    // The citation is shown, not asserted by the model: the agent can see what it rests on.
    expect(screen.getByText('Refund policy')).toBeInTheDocument();
    expect(screen.getByText(/sending it is your decision/i)).toBeInTheDocument();
    // Reading a draft sends nothing.
    expect(writes).toHaveLength(0);

    await userEvent.click(screen.getByRole('button', { name: 'Send reply' }));

    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toEqual({
      path: '/workspaces/w1/tickets/t1/messages/',
      body: { body: DRAFT_WITH_SOURCE.draft_text, visibility: 'public_reply' },
    });
    expect(await screen.findByText('Reply sent.')).toBeInTheDocument();
    // The text is cleared once it has become a reply, so it cannot be sent twice by accident.
    expect(editor).toHaveValue('');
    await expectNoAxeViolations();
  });

  it('shows the classification suggestion and applies it to the ticket', async () => {
    mockTicket({
      ai: { classification: CLASSIFICATION, draft: null },
      onWrite: (path, method) => {
        expect(method).toBe('PATCH');
        expect(path).toBe('/workspaces/w1/tickets/t1/');
        return { ...TICKET, category: 'billing', priority: 'high', version: 2 };
      },
    });

    renderDetail();

    expect(await screen.findByText(/customer reports a duplicate charge/i)).toBeInTheDocument();
    expect(screen.getByText('Category: billing')).toBeInTheDocument();
    expect(screen.getByText('Sentiment: Negative')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Apply suggestion' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/w1/tickets/t1/',
        expect.objectContaining({
          method: 'PATCH',
          // The suggestion becomes a normal field edit under the version the screen read.
          body: { category: 'billing', priority: 'high' },
          ifMatch: 1,
        }),
      );
    });
    // Applied once: the button says so and cannot rewrite the same values.
    expect(await screen.findByRole('button', { name: 'Applied' })).toBeDisabled();
  });

  it('shows the suggestion without offering to apply it when the role cannot edit', async () => {
    // Signed in, but with no membership row here: there is no role to edit with.
    mockTicket({ user: OWNER, members: [AGENT_ROW], ai: { classification: CLASSIFICATION } });

    renderDetail();

    expect(await screen.findByText(/customer reports a duplicate charge/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apply suggestion' })).toBeDisabled();
  });

  it('warns when the draft rests on no knowledge article', async () => {
    mockTicket({ ai: { draft: { ...DRAFT_WITH_SOURCE, source_articles: [] } } });

    renderDetail();

    expect(
      await screen.findByText(/no knowledge article supports this draft/i),
    ).toBeInTheDocument();
  });

  it('requests a draft and reports that it is queued', async () => {
    const queued = {
      ...DRAFT_WITH_SOURCE,
      status: 'pending',
      draft_text: '',
      source_articles: [],
    };
    mockTicket({
      ai: { draft: null },
      onWrite: (path, method) => {
        expect(method).toBe('POST');
        expect(path).toBe('/workspaces/w1/tickets/t1/ai-draft/');
        return queued;
      },
    });

    renderDetail();

    await userEvent.click(await screen.findByRole('button', { name: 'Generate draft' }));

    expect(await screen.findByText(/waiting for a worker/i)).toBeInTheDocument();
    // Still a draft, and still nothing sent.
    expect(screen.queryByText('Reply sent.')).not.toBeInTheDocument();
  });
});

describe('TicketDetailPage timeline', () => {
  it('offers the empty state when nothing has been written yet', async () => {
    mockTicket({ messages: [] });

    renderDetail();

    expect(await screen.findByText('Nothing here yet')).toBeInTheDocument();
  });

  it('says so when the conversation is longer than one page', async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path === '/auth/me/') {
        return Promise.resolve(OWNER);
      }
      if (path.startsWith('/workspaces/w1/members/')) {
        return Promise.resolve(page([OWNER_ROW, AGENT_ROW]));
      }
      if (path === '/workspaces/w1/tickets/t1/') {
        return Promise.resolve(TICKET);
      }
      return Promise.resolve({ ...page([PUBLIC_REPLY]), count: 150 });
    });

    renderDetail();

    expect(await screen.findByText(/more than one page/i)).toBeInTheDocument();
    const timeline = screen.getByText('Conversation').parentElement;
    expect(within(timeline as HTMLElement).getByText('Public reply')).toBeInTheDocument();
  });
});
