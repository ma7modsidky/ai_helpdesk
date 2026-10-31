import { describe, expect, it } from 'vitest';

import ar from './locales/ar.json';
import en from './locales/en.json';

/**
 * A missing translation must fail the build, not reach a user.
 *
 * Review does not catch this reliably: a key added in one language and forgotten in the
 * other renders as a raw identifier, which only shows up if someone happens to look at that
 * screen in that language. Plural suffixes are normalized away first, because i18next's
 * suffixes are language-specific by design — English has `_one`/`_other`, Arabic has six
 * categories — so the requirement is that both locales define the base key, not that they
 * enumerate the same suffixes.
 */
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;

function flatten(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) {
    return [prefix.replace(PLURAL_SUFFIX, '')];
  }
  return Object.entries(value).flatMap(([key, child]) =>
    flatten(child, prefix === '' ? key : `${prefix}.${key}`),
  );
}

function collectStrings(value: unknown, prefix = '', found: Map<string, string> = new Map()) {
  if (typeof value === 'string') {
    found.set(prefix, value);
    return found;
  }
  if (typeof value === 'object' && value !== null) {
    for (const [key, child] of Object.entries(value)) {
      collectStrings(child, prefix === '' ? key : `${prefix}.${key}`, found);
    }
  }
  return found;
}

describe('catalog parity', () => {
  it('defines the same key set in English and Arabic', () => {
    const englishKeys = new Set(flatten(en));
    const arabicKeys = new Set(flatten(ar));

    const missingInArabic = [...englishKeys].filter((key) => !arabicKeys.has(key));
    const missingInEnglish = [...arabicKeys].filter((key) => !englishKeys.has(key));

    expect(missingInArabic, `Untranslated in ar: ${missingInArabic.join(', ')}`).toEqual([]);
    expect(missingInEnglish, `Unknown in en: ${missingInEnglish.join(', ')}`).toEqual([]);
  });

  it('has no empty or whitespace-only values', () => {
    for (const [locale, catalog] of [
      ['en', en],
      ['ar', ar],
    ] as const) {
      const empty = [...collectStrings(catalog)]
        .filter(([, value]) => value.trim().length === 0)
        .map(([key]) => `${locale}:${key}`);
      expect(empty, `Empty translations: ${empty.join(', ')}`).toEqual([]);
    }
  });

  it('leaves no untranslated placeholder in the Arabic catalog', () => {
    // Keys whose value is identical to English are legitimate for endonyms and product
    // nouns; anything else identical is a copy-paste that was never translated.
    const allowedIdentical = new Set([
      'common.appName',
      'common.language.en',
      'common.language.ar',
      'auth.fields.email',
    ]);
    const english = collectStrings(en);
    const arabic = collectStrings(ar);
    const suspicious = [...arabic]
      .filter(
        ([key, value]) =>
          english.get(key) === value && !allowedIdentical.has(key) && /[A-Za-z]/.test(value),
      )
      .map(([key]) => key);

    expect(suspicious, `Possibly untranslated: ${suspicious.join(', ')}`).toEqual([]);
  });
});
