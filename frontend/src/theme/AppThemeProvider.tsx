import { CacheProvider } from '@emotion/react';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import { useEffect, useMemo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import {
  applyDocumentLocale,
  DEFAULT_LOCALE,
  directionFor,
  isSupportedLocale,
  type SupportedLocale,
} from '@/i18n/locale';

import { createAppTheme } from './index';
import { cacheForDirection } from './rtl';

/**
 * The single place that changes when the language changes (ADR-031): the document's
 * `lang` and `dir`, the theme's direction, and the Emotion cache whose stylis plugin
 * flips physical CSS.
 *
 * `defaultMode="system"` keeps the OS preference as the default; MUI persists an
 * explicit choice under `mui-mode` and cross-syncs it between tabs.
 */
export function AppThemeProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();

  const locale: SupportedLocale = isSupportedLocale(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : isSupportedLocale(i18n.language)
      ? i18n.language
      : DEFAULT_LOCALE;
  const direction = directionFor(locale);

  const theme = useMemo(() => createAppTheme({ direction, locale }), [direction, locale]);

  useEffect(() => {
    applyDocumentLocale(locale);
  }, [locale]);

  return (
    <CacheProvider value={cacheForDirection(direction)}>
      <ThemeProvider theme={theme} defaultMode="system">
        <CssBaseline />
        {children}
      </ThemeProvider>
    </CacheProvider>
  );
}
