import { render, type RenderResult } from '@testing-library/react';
import type { QueryClient } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { AppProviders } from '@/app/AppProviders';
import { createI18nInstance } from '@/i18n';
import type { SupportedLocale } from '@/i18n/locale';
import { createQueryClient } from '@/lib/api/queryClient';

const DEFAULT_ROUTE = '/';

export interface RenderOptions {
  readonly locale?: SupportedLocale;
  readonly route?: string;
  /** Route pattern for a component that reads `useParams`, e.g. `/app/:workspaceId/inbox`. */
  readonly path?: string;
}

interface ProviderHandles {
  readonly queryClient: QueryClient;
}

/**
 * A query client with the application's error handling but no retries.
 *
 * The retry policy in production waits a second before the second attempt, which would add
 * a second to every failure case in the suite for no benefit: the tests that care about the
 * retry policy are the client's own, and they assert it directly.
 */
function createTestQueryClient(): QueryClient {
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({
    ...queryClient.getDefaultOptions(),
    queries: { ...queryClient.getDefaultOptions().queries, retry: false, staleTime: 0 },
  });
  return queryClient;
}

function buildTree(
  children: ReactNode,
  { locale = 'en', route = DEFAULT_ROUTE, path }: RenderOptions,
): { tree: ReactElement; handles: ProviderHandles } {
  const i18n = createI18nInstance(locale);
  const queryClient = createTestQueryClient();

  const routed = path ? (
    <Routes>
      <Route path={path} element={children} />
    </Routes>
  ) : (
    children
  );

  return {
    tree: (
      <AppProviders i18n={i18n} queryClient={queryClient}>
        <MemoryRouter initialEntries={[route]}>{routed}</MemoryRouter>
      </AppProviders>
    ),
    handles: { queryClient },
  };
}

/**
 * Render a component with the application's real providers (i18n, query client, theme,
 * direction, error boundary) and a fresh cache per test.
 *
 * The i18n instance is built per render rather than shared, so a test that switches to
 * Arabic cannot change what the next test sees.
 */
export function renderWithProviders(
  ui: ReactElement,
  options: RenderOptions = {},
): RenderResult & ProviderHandles {
  const { tree, handles } = buildTree(ui, options);
  return { ...render(tree), ...handles };
}

/** Render the real route table, for navigation and direction coverage. */
export function renderRoutes(
  routes: ReactElement,
  options: RenderOptions = {},
): RenderResult & ProviderHandles {
  const i18n = createI18nInstance(options.locale ?? 'en');
  const queryClient = createTestQueryClient();
  return {
    ...render(
      <AppProviders i18n={i18n} queryClient={queryClient}>
        <MemoryRouter initialEntries={[options.route ?? DEFAULT_ROUTE]}>{routes}</MemoryRouter>
      </AppProviders>,
    ),
    queryClient,
  };
}
