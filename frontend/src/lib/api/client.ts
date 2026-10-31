/**
 * The only module that calls `fetch` (07 §7.1).
 *
 * Responsibilities: same-origin credentials, the CSRF token on every state-changing
 * request (fetched once and refreshed if the API rejects it), `If-Match` for ticket
 * field edits, and turning every failure into an `ApiError`. It never logs a request or
 * response body — a ticket subject is customer data, and the request ID is enough to
 * find the server-side record.
 */

import { ApiError, networkError, toApiError } from './errors';

const API_PREFIX = '/api/v1';

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

export interface RequestOptions {
  readonly method?: HttpMethod;
  readonly body?: unknown;
  readonly signal?: AbortSignal | undefined;
  /** Optimistic-concurrency token for ticket field edits (ADR-022). */
  readonly ifMatch?: number | undefined;
  /** Extra headers, used by tests and by nothing else today. */
  readonly headers?: Record<string, string> | undefined;
}

let csrfToken: string | null = null;

/**
 * Fetch a fresh CSRF token. The API sets the httpOnly cookie and returns the value to
 * send as a header, so JavaScript never reads the cookie itself.
 *
 * A body that is not the expected JSON (a proxy error page, a 204) must not surface as a
 * `SyntaxError`: it becomes the same typed failure as any other unusable answer.
 */
export async function fetchCsrfToken(): Promise<string> {
  const response = await send('/auth/csrf/', { method: 'GET' }, { csrf: false });
  if (!response.ok) {
    throw toApiError(response, await readBody(response));
  }
  const payload = parseJson(await readBody(response));
  const token =
    payload && typeof payload === 'object' && 'csrf_token' in payload
      ? (payload as { csrf_token?: unknown }).csrf_token
      : undefined;
  if (typeof token !== 'string' || token.length === 0) {
    throw new ApiError({
      status: 0,
      code: 'csrf_unavailable',
      message: 'The CSRF token could not be read.',
    });
  }
  csrfToken = token;
  return csrfToken;
}

/**
 * Read a body exactly once.
 *
 * The response is consumed into text rather than cloned: cloning a body and reading both
 * branches is legal per the fetch spec but is not reliably supported by every runtime this
 * code runs on (jsdom under test, browsers in use), and one read makes the behaviour
 * independent of that.
 */
async function readBody(response: Response): Promise<string> {
  if (response.status === 204) {
    return '';
  }
  try {
    return await response.text();
  } catch {
    return '';
  }
}

function parseJson(text: string): unknown {
  if (text.length === 0) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

/** Replace the token, for example with the rotated one a login response returns. */
export function setCsrfToken(value: string | null): void {
  csrfToken = value;
}

export function clearCsrfToken(): void {
  csrfToken = null;
}

export function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? '';
  return `${base}${API_PREFIX}${path}`;
}

function buildInit(
  path: string,
  options: RequestOptions,
  token: string | null,
): { url: string; init: RequestInit } {
  const method = options.method ?? 'GET';
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...options.headers,
  };
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  if (token !== null) {
    headers['X-CSRFToken'] = token;
  }
  if (options.ifMatch !== undefined) {
    headers['If-Match'] = `"${options.ifMatch}"`;
  }

  const init: RequestInit = {
    method,
    headers,
    credentials: 'include',
  };
  if (options.body !== undefined) {
    init.body = JSON.stringify(options.body);
  }
  if (options.signal) {
    init.signal = options.signal;
  }
  return { url: apiUrl(path), init };
}

async function send(
  path: string,
  options: RequestOptions,
  { csrf }: { csrf: boolean },
): Promise<Response> {
  const method = options.method ?? 'GET';
  const token = csrf && method !== 'GET' ? (csrfToken ?? (await fetchCsrfToken())) : null;
  const { url, init } = buildInit(path, options, token);
  try {
    return await fetch(url, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    throw networkError();
  }
}

function isStateChanging(method: HttpMethod): boolean {
  return method !== 'GET';
}

/**
 * Perform an API request and return its parsed body.
 *
 * A `403 csrf_failed` is the one failure this client repairs on its own: the token can
 * expire while a tab is open, and the API says exactly that, so the request is retried
 * once with a fresh token. Everything else is handed to the caller untouched.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  let response = await send(path, options, { csrf: true });

  if (isStateChanging(method) && response.status === 403) {
    const failure = toApiError(response, await readBody(response));
    if (failure.code === 'csrf_failed') {
      csrfToken = null;
      await fetchCsrfToken();
      response = await send(path, options, { csrf: true });
    } else {
      throw failure;
    }
  }

  if (!response.ok) {
    throw toApiError(response, await readBody(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await readBody(response);
  if (text.length === 0) {
    return undefined as T;
  }
  const parsed = parseJson(text);
  if (parsed === null) {
    // A 2xx body that is not JSON means the client cannot trust what it received; treat it
    // as a failure rather than handing an undefined value to a screen.
    throw new ApiError({
      status: response.status,
      code: 'unreadable_response',
      message: 'The server response could not be read.',
      requestId: response.headers.get('X-Request-ID'),
    });
  }
  return parsed as T;
}
