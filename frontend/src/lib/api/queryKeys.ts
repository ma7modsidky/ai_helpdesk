/**
 * Query keys, in one place (07 §7.3).
 *
 * Every workspace-scoped key includes the workspace id. That is not decoration: without
 * it, switching workspaces could serve a cached list belonging to the previous tenant,
 * which is the one cache bug in this application that would matter.
 */

export const queryKeys = {
  session: ['session'] as const,
  workspaces: ['workspaces'] as const,
  /** Every member of the workspace, for role lookups and assignee options. */
  workspaceMembers: (workspaceId: string) => ['workspace', workspaceId, 'members', 'all'] as const,
  members: (workspaceId: string, page: number) =>
    ['workspace', workspaceId, 'members', { page }] as const,
  invitations: (workspaceId: string, status: string, page: number) =>
    ['workspace', workspaceId, 'invitations', { status, page }] as const,
  tickets: (workspaceId: string, filters: unknown) =>
    ['workspace', workspaceId, 'tickets', filters] as const,
  ticket: (workspaceId: string, ticketId: string) =>
    ['workspace', workspaceId, 'ticket', ticketId] as const,
  ticketMessages: (workspaceId: string, ticketId: string, page: number) =>
    ['workspace', workspaceId, 'ticket', ticketId, 'messages', { page }] as const,
  /** The ticket's AI jobs; separate from the ticket so a draft poll never refetches it. */
  ticketAIStatus: (workspaceId: string, ticketId: string) =>
    ['workspace', workspaceId, 'ticket', ticketId, 'ai'] as const,
};

/** Prefixes for invalidating every cached page of a workspace-scoped collection. */
export const queryKeyPrefixes = {
  members: (workspaceId: string) => ['workspace', workspaceId, 'members'] as const,
  invitations: (workspaceId: string) => ['workspace', workspaceId, 'invitations'] as const,
  tickets: (workspaceId: string) => ['workspace', workspaceId, 'tickets'] as const,
};
