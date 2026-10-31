import { describe, expect, it } from 'vitest';

import {
  ApiError,
  errorMessageKey,
  isApiError,
  isForbidden,
  isNotFound,
  networkError,
  toApiError,
} from './errors';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 400,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
}

/** Read the body the way the client does, then build the error from it. */
async function errorFrom(response: Response): Promise<ApiError> {
  return toApiError(response, await response.text());
}

describe('ApiError.kind', () => {
  it('maps each status to the situation a screen distinguishes', () => {
    expect(new ApiError({ status: 0, code: 'network_error', message: '' }).kind).toBe('network');
    expect(new ApiError({ status: 400, code: 'validation_error', message: '' }).kind).toBe(
      'validation',
    );
    expect(new ApiError({ status: 401, code: 'not_authenticated', message: '' }).kind).toBe(
      'unauthorized',
    );
    expect(new ApiError({ status: 403, code: 'permission_denied', message: '' }).kind).toBe(
      'forbidden',
    );
    expect(new ApiError({ status: 404, code: 'not_found', message: '' }).kind).toBe('notFound');
    expect(new ApiError({ status: 409, code: 'conflict', message: '' }).kind).toBe('conflict');
    expect(new ApiError({ status: 429, code: 'throttled', message: '' }).kind).toBe('throttled');
    expect(new ApiError({ status: 500, code: 'internal_error', message: '' }).kind).toBe('server');
  });
});

describe('fieldErrors', () => {
  it('flattens string, list, and numeric details', () => {
    const error = new ApiError({
      status: 400,
      code: 'validation_error',
      message: 'The request was invalid.',
      details: { email: ['Enter a valid email address.'], slug: 'This slug is already taken.' },
    });
    expect(error.fieldErrors()).toEqual({
      email: 'Enter a valid email address.',
      slug: 'This slug is already taken.',
    });
  });

  it('exposes the current version from a stale edit', () => {
    const error = new ApiError({
      status: 409,
      code: 'conflict',
      message: 'The object changed since it was read.',
      details: { version: 7 },
    });
    expect(error.currentVersion()).toBe(7);
  });

  it('returns nothing when details are absent or the wrong shape', () => {
    expect(new ApiError({ status: 400, code: 'x', message: '' }).fieldErrors()).toEqual({});
    const listDetails = new ApiError({ status: 400, code: 'x', message: '', details: [1, 2] });
    expect(listDetails.fieldErrors()).toEqual({});
    expect(listDetails.currentVersion()).toBeNull();
  });
});

describe('toApiError', () => {
  it('reads code, message, request id, details, and the retry window', async () => {
    const error = await errorFrom(
      jsonResponse(
        {
          error: {
            code: 'throttled',
            message: 'Too many requests.',
            request_id: 'req-1',
            details: { retry: 30 },
          },
        },
        { status: 429, headers: { 'Retry-After': '30' } },
      ),
    );

    expect(error.status).toBe(429);
    expect(error.code).toBe('throttled');
    expect(error.requestId).toBe('req-1');
    expect(error.details).toEqual({ retry: 30 });
    expect(error.retryAfterSeconds).toBe(30);
    expect(error.kind).toBe('throttled');
  });

  it('survives a response whose body is not the envelope', async () => {
    const error = await errorFrom(new Response('<html>gateway</html>', { status: 502 }));
    expect(error.status).toBe(502);
    expect(error.code).toBe('http_error');
    expect(error.requestId).toBeNull();
    expect(error.retryAfterSeconds).toBeNull();
  });
});

describe('errorMessageKey', () => {
  it('points at the catalog key for the situation', () => {
    expect(errorMessageKey(networkError())).toBe('errors.network');
    expect(errorMessageKey(new ApiError({ status: 403, code: 'x', message: '' }))).toBe(
      'errors.forbidden',
    );
    expect(errorMessageKey(new Error('boom'))).toBe('errors.unexpected');
    expect(errorMessageKey('not an error')).toBe('errors.unexpected');
  });
});

describe('guards', () => {
  it('recognises an ApiError and nothing else', () => {
    expect(isApiError(networkError())).toBe(true);
    expect(isApiError(new Error(''))).toBe(false);
    expect(isApiError(null)).toBe(false);
  });

  it('answers the two refusals screens branch on', () => {
    expect(isForbidden(new ApiError({ status: 403, code: 'x', message: '' }))).toBe(true);
    expect(isNotFound(new ApiError({ status: 404, code: 'x', message: '' }))).toBe(true);
    expect(isNotFound(networkError())).toBe(false);
  });
});
