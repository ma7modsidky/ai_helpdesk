import { describe, expect, it } from 'vitest';

import {
  applyDocumentLocale,
  directionFor,
  isSupportedLocale,
  LOCALE_STORAGE_KEY,
  matchLocale,
  persistLocale,
  resolveLocale,
  resolveLocaleFromBrowser,
} from './locale';

describe('matchLocale', () => {
  it('reduces a regional tag to a shipped locale', () => {
    expect(matchLocale('ar-EG')).toBe('ar');
    expect(matchLocale('en-GB')).toBe('en');
    expect(matchLocale('  AR  ')).toBe('ar');
  });

  it('returns null for an unsupported or missing language', () => {
    expect(matchLocale('fr')).toBeNull();
    expect(matchLocale('')).toBeNull();
    expect(matchLocale(null)).toBeNull();
    expect(matchLocale(undefined)).toBeNull();
  });
});

describe('resolveLocale', () => {
  it('prefers the query parameter over everything else', () => {
    expect(resolveLocale({ query: 'ar', stored: 'en', languages: ['en-US'] })).toBe('ar');
  });

  it('falls back to the stored choice, then the browser languages', () => {
    expect(resolveLocale({ query: 'fr', stored: 'ar', languages: ['en-US'] })).toBe('ar');
    expect(resolveLocale({ stored: 'fr', languages: ['ar-SA', 'en'] })).toBe('ar');
  });

  it('keeps walking the browser languages past an unsupported one', () => {
    expect(resolveLocale({ languages: ['de-DE', 'ar-EG', 'en'] })).toBe('ar');
  });

  it('defaults to English when nothing matches', () => {
    expect(resolveLocale({ query: 'fr', stored: 'es', languages: ['de'] })).toBe('en');
    expect(resolveLocale()).toBe('en');
  });
});

describe('resolveLocaleFromBrowser', () => {
  it('reads the ?lang= parameter from the search string', () => {
    expect(resolveLocaleFromBrowser('?lang=ar')).toBe('ar');
  });

  it('uses the stored choice when no parameter is present', () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'ar');
    expect(resolveLocaleFromBrowser('')).toBe('ar');
  });
});

describe('directionFor', () => {
  it('marks Arabic right-to-left and English left-to-right', () => {
    expect(directionFor('ar')).toBe('rtl');
    expect(directionFor('en')).toBe('ltr');
  });
});

describe('persistence and document application', () => {
  it('stores the choice and ignores a storage failure', () => {
    persistLocale('ar');
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('ar');
  });

  it('writes both lang and dir onto the document element', () => {
    applyDocumentLocale('ar');
    expect(document.documentElement.lang).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');

    applyDocumentLocale('en');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
  });
});

describe('isSupportedLocale', () => {
  it('narrows only the shipped locales', () => {
    expect(isSupportedLocale('ar')).toBe(true);
    expect(isSupportedLocale('fr')).toBe(false);
    expect(isSupportedLocale(undefined)).toBe(false);
    expect(isSupportedLocale(42)).toBe(false);
  });
});
