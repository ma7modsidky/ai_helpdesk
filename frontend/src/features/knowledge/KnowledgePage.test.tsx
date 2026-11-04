import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api/client', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiRequest: vi.fn(),
}));

vi.mock('@/features/auth/useSession', () => ({
  useSession: () => ({ data: { id: 'u1' } }),
}));

const membership = vi.hoisted(() => ({ role: 'owner' }));

vi.mock('@/lib/workspaceMembers', () => ({
  useMyMembership: () => ({
    membership: { role: membership.role },
    isLoading: false,
    error: null,
    refetch: () => undefined,
  }),
}));

import { apiRequest } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';
import { expectNoAxeViolations } from '@/test/axe';
import { renderWithProviders } from '@/test/renderWithProviders';

import { KnowledgePage } from './KnowledgePage';

const mockedRequest = vi.mocked(
  apiRequest as unknown as (path: string, options?: { method?: string }) => Promise<unknown>,
);

const ARTICLE = {
  id: 'a1',
  title: 'Refund policy',
  body: 'Refunds are reviewed within five business days.',
  status: 'published',
  version: 1,
  author_id: 'u1',
  published_at: '2026-03-01T08:00:00Z',
  archived_at: null,
  index_status: 'succeeded',
  indexed_version: 1,
  index_attempts: 1,
  index_error: '',
  indexed_at: '2026-03-01T08:00:05Z',
  chunk_count: 1,
  created_at: '2026-03-01T08:00:00Z',
  updated_at: '2026-03-02T08:00:00Z',
};

const DRAFT = {
  ...ARTICLE,
  id: 'a2',
  title: 'Shipping times',
  status: 'draft',
  index_status: 'pending',
  indexed_version: null,
  chunk_count: 0,
  published_at: null,
};

const PAGE = (results: readonly unknown[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

function renderKnowledge(locale: 'en' | 'ar' = 'en') {
  return renderWithProviders(<KnowledgePage />, {
    locale,
    route: '/app/w1/knowledge',
    path: '/app/:workspaceId/knowledge',
  });
}

beforeEach(() => {
  mockedRequest.mockReset();
  membership.role = 'owner';
});

describe('KnowledgePage', () => {
  it('lists articles with their publication and indexing state', async () => {
    mockedRequest.mockResolvedValue(PAGE([ARTICLE]));

    renderKnowledge();

    expect(await screen.findByRole('heading', { name: 'Knowledge base' })).toBeInTheDocument();
    expect(await screen.findByText('Refund policy')).toBeInTheDocument();
    expect(screen.getByText('Published')).toBeInTheDocument();
    expect(screen.getByText('Indexed')).toBeInTheDocument();
    // The rule that governs retrieval is stated, not implied.
    expect(screen.getByText(/only published articles are used/i)).toBeInTheDocument();
    await expectNoAxeViolations();
  });

  it('asks the server for the workspace and the first page', async () => {
    mockedRequest.mockResolvedValue(PAGE([]));

    renderKnowledge();

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/w1/articles/?page=1&page_size=25',
        expect.anything(),
      );
    });
  });

  it('sends the status filter to the server', async () => {
    mockedRequest.mockResolvedValue(PAGE([]));

    renderKnowledge();
    await screen.findByText('No articles yet');

    await userEvent.click(screen.getByLabelText('Status'));
    await userEvent.click(await screen.findByRole('option', { name: 'Draft' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/w1/articles/?status=draft&page=1&page_size=25',
        expect.anything(),
      );
    });
  });

  it('tells a reader without the publish capability why the controls are absent', async () => {
    membership.role = 'agent';
    mockedRequest.mockResolvedValue(PAGE([ARTICLE]));

    renderKnowledge();

    expect(
      await screen.findByText(/you can read articles but not add or publish/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New article' })).not.toBeInTheDocument();
  });

  it('has a distinct empty state', async () => {
    mockedRequest.mockResolvedValue(PAGE([]));

    renderKnowledge();

    expect(await screen.findByText('No articles yet')).toBeInTheDocument();
    expect(
      screen.getByText(/publish an article so the assistant can cite it/i),
    ).toBeInTheDocument();
  });

  it('offers a retry when the list cannot be loaded', async () => {
    mockedRequest.mockRejectedValue(
      new ApiError({ status: 403, code: 'permission_denied', message: 'Denied.' }),
    );

    renderKnowledge();

    expect(await screen.findByText(/role does not allow/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('creates a draft article and reports that indexing is still running', async () => {
    mockedRequest.mockImplementation((_path: string, options?: { method?: string }) => {
      if (options?.method === 'POST') {
        return Promise.resolve({
          ...DRAFT,
          title: 'Charging policy',
          body: 'Charges are reviewed.',
        });
      }
      return Promise.resolve(PAGE([ARTICLE]));
    });

    renderKnowledge();
    await userEvent.click(await screen.findByRole('button', { name: 'New article' }));

    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/^Title/), 'Charging policy');
    await userEvent.type(within(dialog).getByLabelText(/^Body/), 'Charges are reviewed.');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith('/workspaces/w1/articles/', {
        method: 'POST',
        body: { title: 'Charging policy', body: 'Charges are reviewed.' },
      });
    });
    expect(await screen.findByText(/saved\. indexing continues/i)).toBeInTheDocument();
    expect(screen.getByText('Queued')).toBeInTheDocument();
  });

  it('surfaces a lifecycle refusal instead of hiding it', async () => {
    mockedRequest.mockImplementation((path: string, options?: { method?: string }) => {
      if (options?.method === 'POST' && path.endsWith('/publish/')) {
        return Promise.reject(
          new ApiError({ status: 409, code: 'conflict', message: 'Conflict.' }),
        );
      }
      return Promise.resolve(PAGE([DRAFT]));
    });

    renderKnowledge();
    await userEvent.click(await screen.findByRole('button', { name: 'Shipping times' }));

    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish' }));

    expect(await screen.findByText(/current state does not allow/i)).toBeInTheDocument();
  });

  it('guards unsaved edits before the editor closes', async () => {
    mockedRequest.mockResolvedValue(PAGE([ARTICLE]));

    renderKnowledge();
    await userEvent.click(await screen.findByRole('button', { name: 'Refund policy' }));

    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/^Title/), ' updated');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Close' }));

    expect(await screen.findByText('Discard changes?')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Discard changes' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('archives a published article and says it is no longer indexed', async () => {
    mockedRequest.mockImplementation((path: string, options?: { method?: string }) => {
      if (options?.method === 'POST' && path.endsWith('/publish/')) {
        return Promise.resolve({
          ...ARTICLE,
          status: 'archived',
          index_status: 'pending',
          chunk_count: 0,
        });
      }
      return Promise.resolve(PAGE([ARTICLE]));
    });

    renderKnowledge();
    await userEvent.click(await screen.findByRole('button', { name: 'Refund policy' }));

    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Archive' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith('/workspaces/w1/articles/a1/publish/', {
        method: 'POST',
        body: { status: 'archived' },
      });
    });
    expect(within(dialog).getByText('Archived')).toBeInTheDocument();
    // Archiving means retrieval stops, and the editor says so instead of leaving a chunk count.
    expect(
      await within(dialog).findByText(/not indexed because the article is not published/i),
    ).toBeInTheDocument();
  });

  it('offers a reindex after a failed job and reports the new job state', async () => {
    const FAILED = {
      ...ARTICLE,
      index_status: 'failed',
      indexed_version: 0,
      index_error: 'IndexError',
    };
    mockedRequest.mockImplementation((path: string, options?: { method?: string }) => {
      if (options?.method === 'POST' && path.endsWith('/reindex/')) {
        return Promise.resolve({ ...FAILED, index_status: 'pending', index_error: '' });
      }
      return Promise.resolve(PAGE([FAILED]));
    });

    renderKnowledge();
    await userEvent.click(await screen.findByRole('button', { name: 'Refund policy' }));

    const dialog = await screen.findByRole('dialog');
    // The failure is stated with its exception class, which is all the server stores.
    expect(within(dialog).getByText(/the last attempt failed \(IndexError\)/i)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole('button', { name: 'Reindex' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith('/workspaces/w1/articles/a1/reindex/', {
        method: 'POST',
        body: {},
      });
    });
    expect(await within(dialog).findByText('Queued')).toBeInTheDocument();
    expect(within(dialog).queryByText(/the last attempt failed/i)).not.toBeInTheDocument();
  });

  it("pages with the server's next link rather than slicing the loaded page", async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path.includes('page=2')) {
        return Promise.resolve({
          count: 26,
          next: null,
          previous: 'https://example.test/page=1',
          results: [DRAFT],
        });
      }
      return Promise.resolve({
        count: 26,
        next: 'https://example.test/page=2',
        previous: null,
        results: [ARTICLE],
      });
    });

    renderKnowledge();
    expect(await screen.findByText('Refund policy')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        '/workspaces/w1/articles/?page=2&page_size=25',
        expect.anything(),
      );
    });
    expect(await screen.findByText('Shipping times')).toBeInTheDocument();
  });

  it('renders the Arabic screen with translated labels', async () => {
    mockedRequest.mockResolvedValue(PAGE([ARTICLE]));

    renderKnowledge('ar');

    // Await a data-dependent element: the heading renders before the list does.
    expect(await screen.findByText('منشور')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'قاعدة المعرفة' })).toBeInTheDocument();
    expect(screen.getByText('مفهرس')).toBeInTheDocument();
  });
});
