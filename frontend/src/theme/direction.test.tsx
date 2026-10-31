import { screen, waitFor } from '@testing-library/react';
import type { Theme } from '@mui/material/styles';
import { describe, expect, it } from 'vitest';

import { LoginPage } from '@/features/auth/LoginPage';
import { renderWithProviders } from '@/test/renderWithProviders';

import { createAppTheme } from './index';
import { cacheForDirection, ltrCache, rtlCache } from './rtl';

describe('createAppTheme', () => {
  it('carries the direction into the theme so components flip their internals', () => {
    expect(createAppTheme({ direction: 'rtl', locale: 'ar' }).direction).toBe('rtl');
    expect(createAppTheme({ direction: 'ltr', locale: 'en' }).direction).toBe('ltr');
  });

  it('raises Arabic line heights and removes letter spacing', () => {
    const arabic = createAppTheme({ direction: 'rtl', locale: 'ar' });
    const english = createAppTheme({ direction: 'ltr', locale: 'en' });

    expect(lineHeight(arabic)).toBeGreaterThan(lineHeight(english));
    // Tracking would pull apart the joined letters of Arabic script, so it is zeroed where
    // the script is rendered; the English theme leaves MUI's own tracking in place.
    expect(arabic.typography.body1.letterSpacing).toBe(0);
    expect(arabic.typography.button.letterSpacing).toBe(0);
    expect(english.typography.button?.letterSpacing).not.toBe(0);
    expect(arabic.typography.fontSize).toBeGreaterThan(english.typography.fontSize);
  });

  it('declares both colour schemes so the mode switch needs no re-render', () => {
    const theme = createAppTheme({ direction: 'ltr', locale: 'en' }) as CssVarsThemeShape;
    const schemes = Object.keys(theme.colorSchemes);

    expect(schemes.sort()).toEqual(['dark', 'light']);
    expect(theme.colorSchemes.dark?.palette?.background?.paper).not.toBe(
      theme.colorSchemes.light?.palette?.background?.paper,
    );
  });
});

function lineHeight(theme: Theme): number {
  return Number(theme.typography.body1.lineHeight ?? 0);
}

/** `createTheme` is typed as `Theme`; a theme built with `colorSchemes` is a CSS-vars theme. */
type CssVarsThemeShape = Theme & {
  colorSchemes: Record<string, { palette?: { background?: { paper?: string } } }>;
};

describe('Emotion caches', () => {
  it('selects a distinct cache per direction', () => {
    expect(cacheForDirection('ltr')).toBe(ltrCache);
    expect(cacheForDirection('rtl')).toBe(rtlCache);
    expect(ltrCache.key).not.toBe(rtlCache.key);
  });
});

describe('document direction', () => {
  it('applies rtl and Arabic copy for the Arabic locale', async () => {
    renderWithProviders(<LoginPage />, { locale: 'ar', route: '/login' });

    await waitFor(() => {
      expect(document.documentElement.dir).toBe('rtl');
    });
    expect(document.documentElement.lang).toBe('ar');
    expect(await screen.findByRole('button', { name: 'دخول' })).toBeInTheDocument();
  });

  it('applies ltr and English copy for the English locale', async () => {
    renderWithProviders(<LoginPage />, { locale: 'en', route: '/login' });

    await waitFor(() => {
      expect(document.documentElement.dir).toBe('ltr');
    });
    expect(document.documentElement.lang).toBe('en');
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });
});
