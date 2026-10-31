import type { QueryClient } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

import type { AppI18n } from '@/i18n';

import { AppProviders } from './AppProviders';
import { AppRoutes } from './router';

/**
 * The application with its collaborators injected rather than constructed here: the i18n
 * instance and query client are created once at the entry point, and tests build their own
 * pair so one test's language or cache cannot leak into the next.
 */
export function App({ i18n, queryClient }: { i18n: AppI18n; queryClient: QueryClient }) {
  return (
    <AppProviders i18n={i18n} queryClient={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppProviders>
  );
}
