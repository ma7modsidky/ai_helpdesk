import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeyPrefixes, queryKeys } from '@/lib/api/queryKeys';

import {
  createInvitation,
  listInvitations,
  listMembers,
  resendInvitation,
  revokeInvitation,
  transferOwnership,
  updateMember,
  type InvitationFilter,
  type MemberChange,
} from './api';
import type { MembershipRole } from '@/lib/domain';

export function useMembers(workspaceId: string, page = 1) {
  return useQuery({
    queryKey: queryKeys.members(workspaceId, page),
    queryFn: ({ signal }) => listMembers(workspaceId, page, signal),
    enabled: workspaceId.length > 0,
  });
}

export function useInvitations(workspaceId: string, status: InvitationFilter, page = 1) {
  return useQuery({
    queryKey: queryKeys.invitations(workspaceId, status, page),
    queryFn: ({ signal }) => listInvitations(workspaceId, status, page, signal),
    enabled: workspaceId.length > 0,
  });
}

/**
 * Membership, invitation, and ownership writes all invalidate the member list.
 *
 * A role change moves the caller's own capabilities when the caller is the target, and the
 * member list is what `useMyMembership` reads, so the narrowest correct set is the members
 * prefix plus the invitations the settings screen is showing.
 */
function useMemberWrite<TVariables, TResult>(
  workspaceId: string,
  mutationFn: (variables: TVariables) => Promise<TResult>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.members(workspaceId) });
      void queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.invitations(workspaceId) });
    },
  });
}

export function useChangeMember(workspaceId: string) {
  return useMemberWrite(
    workspaceId,
    ({ membershipId, change }: { membershipId: string; change: MemberChange }) =>
      updateMember(workspaceId, membershipId, change),
  );
}

export function useInviteMember(workspaceId: string) {
  return useMemberWrite(workspaceId, ({ email, role }: { email: string; role: MembershipRole }) =>
    createInvitation(workspaceId, email, role),
  );
}

export function useResendInvitation(workspaceId: string) {
  return useMemberWrite(workspaceId, (invitationId: string) =>
    resendInvitation(workspaceId, invitationId),
  );
}

export function useRevokeInvitation(workspaceId: string) {
  return useMemberWrite(workspaceId, (invitationId: string) =>
    revokeInvitation(workspaceId, invitationId),
  );
}

export function useTransferOwnership(workspaceId: string) {
  return useMemberWrite(workspaceId, (membershipId: string) =>
    transferOwnership(workspaceId, membershipId),
  );
}
