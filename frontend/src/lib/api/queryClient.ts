import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';

import { isApiError } from './errors';
import { queryKeys } from './queryKeys';

/**
 * Server-state defaults (07 §7.3).
 *
 * Reads are cached briefly and never retried when the API has already given a definite
 * answer: retrying a 403 or a 409 would only delay the screen's explanation. Writes are
 * never retried automatically, because a command that failed for a state reason will fail
 * again, and the user's decision is what should change.
 *
 * The caches also carry one cross-cutting rule: a `401` from *any* request means the
 * session is gone, so the session entry is set to `null`. Without it, a background refetch
 * that hits an expired cookie would leave the UI showing a signed-in shell whose every
 * action fails.
 */
export function createQueryClient(): QueryClient {
  const client = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => handleUnauthorized(error, query.queryKey),
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) =>
        handleUnauthorized(error, mutation.options.mutationKey),
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (isApiError(error) && error.status > 0 && error.status < 500) {
            return false;
          }
          return failureCount < 1;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });

  /** Declared after the client it writes into: declarations hoist, and no cache handler
   * can run before the client exists. */
  function handleUnauthorized(error: unknown, key: readonly unknown[] | undefined): void {
    if (!isApiError(error) || error.kind !== 'unauthorized') {
      return;
    }
    // The session query already reports `null` for a signed-out visitor; only other
    // requests need to be translated into that state.
    if (key?.[0] === queryKeys.session[0]) {
      return;
    }
    client.setQueryData(queryKeys.session, null);
  }

  return client;
}
