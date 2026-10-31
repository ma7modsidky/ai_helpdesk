/**
 * Who is in this workspace — a read several screens need.
 *
 * The settings screen lists members with pagination; the ticket detail needs the same
 * people as assignee options; and both the shell and every capability-gated control need the
 * caller's own role. It lives in `lib` because three features read it and a feature may not
 * import another feature's internals (ADR-030), and it is one query so the endpoint is
 * fetched once per workspace rather than once per screen that happens to need it.
 */

import { useQuery } from '@tanstack/react-query';

import { apiRequest } from './api/client';
import { PAGE_SIZE, type Paginated } from './api/pagination';
import { queryKeys } from './api/queryKeys';
import type { MembershipRole } from './domain';

/** A membership row: the caller's relationship to one workspace. */
export interface WorkspaceMember {
  readonly id: string;
  readonly user_id: string;
  readonly email: string;
  readonly role: MembershipRole;
  readonly status: 'active' | 'removed';
  readonly created_at: string;
}

export async function listWorkspaceMembers(
  workspaceId: string,
  signal?: AbortSignal,
): Promise<readonly WorkspaceMember[]> {
  const page = await apiRequest<Paginated<WorkspaceMember>>(
    `/workspaces/${workspaceId}/members/?page_size=${PAGE_SIZE}`,
    { signal },
  );
  return page.results;
}

export function useWorkspaceMembers(workspaceId: string) {
  return useQuery<readonly WorkspaceMember[]>({
    queryKey: queryKeys.workspaceMembers(workspaceId),
    queryFn: ({ signal }) => listWorkspaceMembers(workspaceId, signal),
    enabled: workspaceId.length > 0,
    // Always re-read on mount instead of trusting a cached page: this read decides what the
    // UI offers — who may be assigned, and which capabilities the caller has — and a member
    // who accepted an invitation a minute ago must be assignable without a reload.
    refetchOnMount: 'always',
  });
}

export interface MyMembership {
  readonly membership: WorkspaceMember | null;
  readonly isLoading: boolean;
  readonly error: unknown;
  readonly refetch: () => void;
}

/**
 * The caller's own membership in a workspace.
 *
 * The workspace resource does not carry the caller's role (04 §Workspaces), so the role
 * used for capability-driven UI is read from the member list. That keeps the client from
 * guessing, and it means the role the UI offers controls for is the role the server
 * enforces. The caller's id is a parameter rather than a session read, so this module does
 * not have to know how a session is obtained.
 */
export function useMyMembership(
  workspaceId: string,
  userId: string | null | undefined,
): MyMembership {
  const members = useWorkspaceMembers(workspaceId);
  const membership = members.data?.find((entry) => entry.user_id === userId) ?? null;

  return {
    membership,
    isLoading: members.isLoading,
    error: members.error,
    refetch: () => {
      void members.refetch();
    },
  };
}
