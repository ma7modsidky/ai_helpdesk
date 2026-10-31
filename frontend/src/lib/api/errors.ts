/**
 * The API's uniform error envelope, turned into one typed error (07 §7.1–7.2).
 *
 * Every failure the client can see becomes an `ApiError`: an HTTP error with an
 * envelope, a non-JSON response, and a dropped connection all arrive here as the same
 * type, so no screen has to guess which shape it received.
 */

/** The five situations a screen's copy distinguishes. */
export type ApiErrorKind =
  | 'network'
  | 'validation'
  | 'unauthorized'
  | 'forbidden'
  | 'notFound'
  | 'conflict'
  | 'throttled'
  | 'server'
  | 'unexpected';

export interface ApiErrorInit {
  readonly status: number;
  readonly code: string;
  readonly message: string;
  readonly requestId?: string | null;
  readonly details?: unknown;
  readonly retryAfterSeconds?: number | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown;
  readonly retryAfterSeconds: number | null;

  constructor({
    status,
    code,
    message,
    requestId = null,
    details,
    retryAfterSeconds = null,
  }: ApiErrorInit) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
    this.retryAfterSeconds = retryAfterSeconds;
  }

  get kind(): ApiErrorKind {
    if (this.status === 0) {
      return 'network';
    }
    if (this.code === 'validation_error' || this.status === 400) {
      return 'validation';
    }
    if (this.status === 401) {
      return 'unauthorized';
    }
    if (this.status === 403) {
      return 'forbidden';
    }
    if (this.status === 404) {
      return 'notFound';
    }
    if (this.status === 409) {
      return 'conflict';
    }
    if (this.status === 429) {
      return 'throttled';
    }
    if (this.status >= 500) {
      return 'server';
    }
    return 'unexpected';
  }

  /**
   * Field errors from a `validation_error`, flattened to one message per field.
   * The envelope maps field names to messages or to arrays of them.
   */
  fieldErrors(): Record<string, string> {
    const details = this.details;
    if (!details || typeof details !== 'object' || Array.isArray(details)) {
      return {};
    }
    const fields: Record<string, string> = {};
    for (const [field, value] of Object.entries(details)) {
      if (typeof value === 'string') {
        fields[field] = value;
      } else if (Array.isArray(value) && typeof value[0] === 'string') {
        fields[field] = value[0];
      } else if (typeof value === 'number') {
        // `error.details.version` on a stale If-Match is a number.
        fields[field] = String(value);
      }
    }
    return fields;
  }

  /** The version to reload after a stale ticket edit, when the server reported one. */
  currentVersion(): number | null {
    const raw = this.fieldErrors()['version'];
    if (raw === undefined) {
      return null;
    }
    const parsed = Number.parseInt(raw, 10);
    return Number.isNaN(parsed) ? null : parsed;
  }
}

/** A connection-level failure, wrapped so callers only handle `ApiError`. */
export function networkError(): ApiError {
  return new ApiError({
    status: 0,
    code: 'network_error',
    message: 'The server could not be reached.',
  });
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/** Translation key for a failure's user-facing explanation (07 §2.5). */
export function errorMessageKey(error: unknown): string {
  return isApiError(error) ? `errors.${error.kind}` : 'errors.unexpected';
}

export function isForbidden(error: unknown): boolean {
  return isApiError(error) && error.kind === 'forbidden';
}

export function isNotFound(error: unknown): boolean {
  return isApiError(error) && error.kind === 'notFound';
}

interface Envelope {
  readonly error?: {
    readonly code?: unknown;
    readonly message?: unknown;
    readonly request_id?: unknown;
    readonly details?: unknown;
  };
}

/**
 * Build an `ApiError` from a response and its already-read body.
 *
 * The body is passed in rather than read here so a response is consumed exactly once, and
 * so a body that is not the envelope (a proxy error page, an empty 502) degrades to a
 * generic failure instead of throwing from inside error handling.
 */
export function toApiError(response: Response, bodyText: string): ApiError {
  let payload: Envelope | null = null;
  if (bodyText.length > 0) {
    try {
      payload = JSON.parse(bodyText) as Envelope;
    } catch {
      payload = null;
    }
  }
  const error = payload?.error;
  const retryAfter = Number.parseInt(response.headers.get('Retry-After') ?? '', 10);
  return new ApiError({
    status: response.status,
    code: typeof error?.code === 'string' ? error.code : 'http_error',
    message: typeof error?.message === 'string' ? error.message : response.statusText,
    requestId: typeof error?.request_id === 'string' ? error.request_id : null,
    details: error?.details ?? null,
    retryAfterSeconds: Number.isNaN(retryAfter) ? null : retryAfter,
  });
}
