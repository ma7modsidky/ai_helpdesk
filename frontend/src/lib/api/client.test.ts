import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest, apiUrl, clearCsrfToken } from './client';
import { ApiError } from './errors';

function json(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
}

/**
 * A fresh CSRF response per use. A `Response` body can be read once, so a shared instance
 * would be unusable in the second test that queued it and would fail as a missing token.
 */
function csrfResponse(token = 'token-1'): Response {
  return json({ csrf_token: token });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  clearCsrfToken();
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('apiUrl', () => {
  it('prefixes the versioned API path', () => {
    expect(apiUrl('/auth/me/')).toBe('/api/v1/auth/me/');
  });
});

describe('csrf handling', () => {
  it('fetches a token once and sends it on state-changing requests', async () => {
    fetchMock
      .mockResolvedValueOnce(csrfResponse())
      .mockResolvedValueOnce(json({ user: { id: '1' } }));

    await apiRequest('/auth/login/', { method: 'POST', body: { email: 'a@b.c', password: 'x' } });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/auth/csrf/');
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/login/');
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('include');
    expect((init.headers as Record<string, string>)['X-CSRFToken']).toBe('token-1');
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(init.body).toBe(JSON.stringify({ email: 'a@b.c', password: 'x' }));
  });

  it('does not fetch a token for a read', async () => {
    fetchMock.mockResolvedValueOnce(json({ id: '1' }));

    await apiRequest('/auth/me/');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)['X-CSRFToken']).toBeUndefined();
  });

  it('refreshes an expired token and retries once on csrf_failed', async () => {
    fetchMock
      .mockResolvedValueOnce(csrfResponse())
      .mockResolvedValueOnce(
        json({ error: { code: 'csrf_failed', message: 'no' } }, { status: 403 }),
      )
      .mockResolvedValueOnce(csrfResponse('token-2'))
      .mockResolvedValueOnce(json({ ok: true }));

    const result = await apiRequest<{ ok: boolean }>('/workspaces/', {
      method: 'POST',
      body: { name: 'Acme' },
    });

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    const [, retryInit] = fetchMock.mock.calls[3] as [string, RequestInit];
    expect((retryInit.headers as Record<string, string>)['X-CSRFToken']).toBe('token-2');
  });

  it('does not treat a permission denial as a CSRF failure', async () => {
    fetchMock
      .mockResolvedValueOnce(csrfResponse())
      .mockResolvedValueOnce(
        json({ error: { code: 'permission_denied', message: 'no' } }, { status: 403 }),
      );

    await expect(apiRequest('/workspaces/', { method: 'POST', body: {} })).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe('request options', () => {
  it('sends If-Match quoted, as the API requires for ticket edits', async () => {
    fetchMock.mockResolvedValueOnce(csrfResponse()).mockResolvedValueOnce(json({ id: 't1' }));

    await apiRequest('/workspaces/w1/tickets/t1/', {
      method: 'PATCH',
      body: { subject: 'New' },
      ifMatch: 4,
    });

    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect((init.headers as Record<string, string>)['If-Match']).toBe('"4"');
  });

  it('returns undefined for a 204 with no body', async () => {
    fetchMock
      .mockResolvedValueOnce(csrfResponse())
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(
      apiRequest('/auth/logout/', { method: 'POST', body: {} }),
    ).resolves.toBeUndefined();
  });
});

describe('failures', () => {
  it('throws a typed error carrying the request id', async () => {
    fetchMock.mockResolvedValueOnce(
      json(
        {
          error: {
            code: 'not_found',
            message: 'The requested resource was not found.',
            request_id: 'r-9',
          },
        },
        { status: 404 },
      ),
    );

    await expect(apiRequest('/workspaces/missing/')).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
      requestId: 'r-9',
    });
  });

  it('wraps a connection failure as a network error and keeps aborts separate', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(apiRequest('/auth/me/')).rejects.toMatchObject({
      status: 0,
      code: 'network_error',
    });

    const abort = new DOMException('aborted', 'AbortError');
    fetchMock.mockRejectedValueOnce(abort);
    await expect(apiRequest('/auth/me/')).rejects.toBeInstanceOf(DOMException);
  });

  it('reports a CSRF endpoint that returns no token', async () => {
    fetchMock
      .mockResolvedValueOnce(json({}))
      .mockResolvedValueOnce(json({ error: {} }, { status: 500 }));

    await expect(apiRequest('/workspaces/', { method: 'POST', body: {} })).rejects.toMatchObject({
      code: 'csrf_unavailable',
    });
  });
});

describe('documented behaviour of a failed CSRF fetch', () => {
  it('throws the CSRF failure rather than posting without a token', async () => {
    fetchMock
      .mockResolvedValueOnce(
        json({ error: { code: 'not_found', message: 'gone' } }, { status: 404 }),
      )
      .mockResolvedValueOnce(json({ error: {} }, { status: 500 }));

    await expect(apiRequest('/workspaces/', { method: 'POST', body: {} })).rejects.toMatchObject({
      status: 404,
    });
  });
});
