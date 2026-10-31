import { apiRequest } from '@/lib/api/client';
import type { InvitationState, MembershipRole } from '@/lib/domain';
import type { WorkspaceMember } from '@/lib/workspaceMembers';

import type { Workspace } from '@/features/workspaces/api';

/**
 * The public preview: workspace name, offered role, state, expiry. It deliberately does
 * not return the invited address, so the page cannot confirm whether a given address has
 * an invitation (04 §Invitations, invitee side).
 */
export interface InvitationPreview {
  readonly workspace_name: string;
  readonly role: Exclude<MembershipRole, 'owner'>;
  readonly status: InvitationState;
  readonly expires_at: string;
}

export interface AcceptInvitationResult {
  readonly workspace: Workspace;
  readonly membership: WorkspaceMember;
}

/** The token travels in the body, never in the URL the app requests (ADR-026). */
export async function previewInvitation(
  token: string,
  signal?: AbortSignal,
): Promise<InvitationPreview> {
  return apiRequest<InvitationPreview>('/invitations/preview/', {
    method: 'POST',
    body: { token },
    signal,
  });
}

export async function acceptInvitation(token: string): Promise<AcceptInvitationResult> {
  return apiRequest<AcceptInvitationResult>('/invitations/accept/', {
    method: 'POST',
    body: { token },
  });
}
