import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeys } from '@/lib/api/queryKeys';

import { fetchSession, login, logout, register, type AuthUser, type Credentials } from './api';

/**
 * The session query. `staleTime` is zero because it answers "may this person see this
 * screen", and a stale answer there is a security-relevant UI decision, not a cosmetic
 * one (07 §7.3).
 */
export function useSession() {
  return useQuery<AuthUser | null>({
    queryKey: queryKeys.session,
    queryFn: ({ signal }) => fetchSession(signal),
    staleTime: 0,
    retry: false,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: Credentials) => login(credentials),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.session, user);
    },
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: Credentials) => register(credentials),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.session, user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => logout(),
    onSettled: () => {
      // Drop every cached tenant response on the way out. A queued refetch or a second
      // tab must not be able to render the previous account's tickets.
      queryClient.clear();
    },
  });
}
