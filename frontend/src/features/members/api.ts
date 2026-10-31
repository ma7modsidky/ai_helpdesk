import { apiRequest } from '@/lib/api/client';
import { PAGE_SIZE, type Paginated } from '@/lib/api/pagination';
import type { InvitationState, MembershipRole } from '@/lib/domain';
import type { WorkspaceMember } from '@/lib/workspaceMembers';

/** A membership row as the member list returns it; the same row every other screen reads. */
export type Member = WorkspaceMember;

/** A membership change: a role, a status, or both (the server refuses an empty body). */
export interface MemberChange {
  readonly role?: MembershipRole;
  readonly status?: 'active' | 'removed';
}

/**
 * An invitation row. `status` is the effective state — `pending`, `expired`, `accepted` or
 * `revoked` — because expiry is derived on the server rather than stored.
 */
export interface Invitation {
  readonly id: string;
  readonly email: string;
  readonly role: MembershipRole;
  readonly status: InvitationState;
  readonly expires_at: string;
  readonly created_at: string;
  readonly invited_by: { readonly user_id: string; readonly email: string } | null;
  readonly delivery_status: string;
}

/**
 * The create and resend responses carry `accept_path`, the invitee's route.
 *
 * It is returned exactly once per token (ADR-026), which is why the screen shows it at the
 * moment of creation and never reads it back from a list.
 */
export interface InvitationWithLink extends Invitation {
  readonly accept_path: string;
}

/** Invitations the screen can ask for; `pending` includes live and expired rows. */
export type InvitationFilter = 'pending' | 'accepted' | 'revoked' | 'all';

export interface OwnershipTransferResult {
  readonly owner: Member;
  readonly previous_owner: Member;
}

export async function listMembers(
  workspaceId: string,
  page: number,
  signal?: AbortSignal,
): Promise<Paginated<Member>> {
  return apiRequest<Paginated<Member>>(
    `/workspaces/${workspaceId}/members/?page=${page}&page_size=${PAGE_SIZE}`,
    { signal },
  );
}

export async function updateMember(
  workspaceId: string,
  membershipId: string,
  change: MemberChange,
): Promise<Member> {
  return apiRequest<Member>(`/workspaces/${workspaceId}/members/${membershipId}/`, {
    method: 'PATCH',
    body: change,
  });
}

export async function listInvitations(
  workspaceId: string,
  status: InvitationFilter,
  page: number,
  signal?: AbortSignal,
): Promise<Paginated<Invitation>> {
  const params = new URLSearchParams({
    status,
    page: String(page),
    page_size: String(PAGE_SIZE),
  });
  return apiRequest<Paginated<Invitation>>(
    `/workspaces/${workspaceId}/invitations/?${params.toString()}`,
    { signal },
  );
}

export async function createInvitation(
  workspaceId: string,
  email: string,
  role: MembershipRole,
): Promise<InvitationWithLink> {
  return apiRequest<InvitationWithLink>(`/workspaces/${workspaceId}/invitations/`, {
    method: 'POST',
    body: { email, role },
  });
}

export async function resendInvitation(
  workspaceId: string,
  invitationId: string,
): Promise<InvitationWithLink> {
  return apiRequest<InvitationWithLink>(
    `/workspaces/${workspaceId}/invitations/${invitationId}/resend/`,
    { method: 'POST', body: {} },
  );
}

export async function revokeInvitation(workspaceId: string, invitationId: string): Promise<void> {
  await apiRequest<void>(`/workspaces/${workspaceId}/invitations/${invitationId}/`, {
    method: 'DELETE',
  });
}

export async function transferOwnership(
  workspaceId: string,
  membershipId: string,
): Promise<OwnershipTransferResult> {
  return apiRequest<OwnershipTransferResult>(`/workspaces/${workspaceId}/transfer-ownership/`, {
    method: 'POST',
    body: { membership_id: membershipId },
  });
}
