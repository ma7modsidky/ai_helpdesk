/**
 * Post-authentication navigation.
 *
 * `?next=` is attacker-controllable: whoever sends a victim a link chooses it. Only a
 * same-origin, absolute path is accepted, so a crafted parameter cannot bounce a
 * signed-in user to another origin (07 §10, 10_SECURITY.md).
 */

export const DEFAULT_AUTHENTICATED_PATH = '/app/workspaces';

export function safeRedirectPath(raw: string | null | undefined): string | null {
  if (!raw) {
    return null;
  }
  // A leading slash is required, and `//host` and `/\host` are protocol-relative URLs
  // that a browser would resolve off-origin.
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) {
    return null;
  }
  if (raw.includes('://') || raw.includes('\\')) {
    return null;
  }
  return raw;
}

/** Build the login URL that returns the visitor to where they were heading. */
export function loginPathFor(target: string): string {
  return `/login?next=${encodeURIComponent(target)}`;
}
