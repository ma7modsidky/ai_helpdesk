import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeys } from '@/lib/api/queryKeys';

import { createWorkspace, listWorkspaces, type CreateWorkspaceInput, type Workspace } from './api';

export function useWorkspaces() {
  return useQuery<readonly Workspace[]>({
    queryKey: queryKeys.workspaces,
    queryFn: ({ signal }) => listWorkspaces(signal),
  });
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateWorkspaceInput) => createWorkspace(input),
    onSuccess: () => {
      // The new workspace belongs in the switcher and the picker immediately; the
      // member list for it is fetched on demand by the screen that needs the role.
      void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
    },
  });
}
