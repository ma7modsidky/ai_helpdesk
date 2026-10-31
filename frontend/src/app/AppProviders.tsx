import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';

import { AppThemeProvider } from '@/theme/AppThemeProvider';
import type { AppI18n } from '@/i18n';

import { ErrorBoundary } from './ErrorBoundary';

/**
 * The provider order matters and is deliberate:
 *
 * 1. i18n first, because the theme provider reads the active locale to pick a direction.
 * 2. the query client, so any screen below can read server state.
 * 3. the theme, which also owns the text direction and the Emotion cache.
 * 4. the error boundary last and innermost, so its fallback still renders with a theme and
 *    translated copy.
 */
export function AppProviders({
  i18n,
  queryClient,
  children,
}: {
  i18n: AppI18n;
  queryClient: QueryClient;
  children: ReactNode;
}) {
  return (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={queryClient}>
        <AppThemeProvider>
          <ErrorBoundary>{children}</ErrorBoundary>
        </AppThemeProvider>
      </QueryClientProvider>
    </I18nextProvider>
  );
}
