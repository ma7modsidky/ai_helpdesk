import { apiRequest, clearCsrfToken, setCsrfToken } from '@/lib/api/client';
import { isApiError } from '@/lib/api/errors';

/** The user object the API returns from login, registration, and `/auth/me/`. */
export interface AuthUser {
  readonly id: string;
  readonly email: string;
  readonly is_staff: boolean;
}

interface AuthSessionResponse {
  readonly user: AuthUser;
  readonly csrf_token?: string;
}

export interface Credentials {
  readonly email: string;
  readonly password: string;
}

/**
 * The current session, or `null` when there is none.
 *
 * A `401` here is the expected answer for a signed-out visitor, not a failure, so it is
 * translated to `null` rather than thrown — otherwise every visit to a public page would
 * surface an error state.
 */
export async function fetchSession(signal?: AbortSignal): Promise<AuthUser | null> {
  try {
    return await apiRequest<AuthUser>('/auth/me/', { signal });
  } catch (error) {
    if (isApiError(error) && error.kind === 'unauthorized') {
      return null;
    }
    throw error;
  }
}

/**
 * The session and CSRF token both rotate on login, so the token from the response must
 * replace whatever the client was holding (04 §Authentication flow).
 */
function adoptSession({ user, csrf_token }: AuthSessionResponse): AuthUser {
  setCsrfToken(csrf_token ?? null);
  return user;
}

export async function login(credentials: Credentials): Promise<AuthUser> {
  const response = await apiRequest<AuthSessionResponse>('/auth/login/', {
    method: 'POST',
    body: credentials,
  });
  return adoptSession(response);
}

export async function register(credentials: Credentials): Promise<AuthUser> {
  const response = await apiRequest<AuthSessionResponse>('/auth/register/', {
    method: 'POST',
    body: credentials,
  });
  return adoptSession(response);
}

export async function logout(): Promise<void> {
  await apiRequest<void>('/auth/logout/', { method: 'POST', body: {} });
  clearCsrfToken();
}
