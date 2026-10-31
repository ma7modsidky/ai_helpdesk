/**
 * Locale resolution, persistence, and text direction (ADR-031).
 *
 * The locale is a client-side preference: the API stores none, so resolution happens
 * here and the result is written back to `localStorage` for the next visit. The same
 * rules are duplicated as a tiny inline script in `index.html` so the first paint has
 * the right direction; keep the two in step, and treat this module as the source of
 * truth because it is the one the tests cover.
 */

export const SUPPORTED_LOCALES = ['en', 'ar'] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: SupportedLocale = 'en';
export const LOCALE_STORAGE_KEY = 'resolveai.locale';

export type Direction = 'ltr' | 'rtl';

const RTL_LOCALES: readonly SupportedLocale[] = ['ar'];

export function isSupportedLocale(value: unknown): value is SupportedLocale {
  return typeof value === 'string' && SUPPORTED_LOCALES.some((locale) => locale === value);
}

export function directionFor(locale: SupportedLocale): Direction {
  return RTL_LOCALES.includes(locale) ? 'rtl' : 'ltr';
}

/**
 * Reduce a BCP-47 tag to a shipped locale.
 *
 * `ar-EG` matches `ar` and `en-GB` matches `en`, so a regional preference is not
 * thrown away in favour of the fallback. An unsupported language returns `null`
 * so the caller can keep walking the list.
 */
export function matchLocale(tag: string | null | undefined): SupportedLocale | null {
  if (!tag) {
    return null;
  }
  const base = tag.trim().toLowerCase().split('-')[0];
  return isSupportedLocale(base) ? base : null;
}

export interface LocaleSources {
  /** Value of a `?lang=` parameter, when present. */
  readonly query?: string | null | undefined;
  /** Value previously persisted by this app. */
  readonly stored?: string | null | undefined;
  /** Browser languages, most preferred first. */
  readonly languages?: readonly (string | null | undefined)[] | undefined;
}

/**
 * Resolve the active locale: explicit query parameter, then the stored choice, then
 * the browser's preference, then `en` (07 §3.2). Exported pure so every branch can be
 * tested without touching `window`.
 */
export function resolveLocale({
  query = null,
  stored = null,
  languages = [],
}: LocaleSources = {}): SupportedLocale {
  const fromQuery = matchLocale(query);
  if (fromQuery) {
    return fromQuery;
  }
  const fromStorage = matchLocale(stored);
  if (fromStorage) {
    return fromStorage;
  }
  for (const language of languages) {
    const match = matchLocale(language);
    if (match) {
      return match;
    }
  }
  return DEFAULT_LOCALE;
}

/** The three sources above, read from the browser. */
export function resolveLocaleFromBrowser(search = window.location.search): SupportedLocale {
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
  } catch {
    // Private mode or storage disabled: fall through to the browser's languages.
  }
  return resolveLocale({
    query: new URLSearchParams(search).get('lang'),
    stored,
    languages: navigator.languages?.length ? navigator.languages : [navigator.language],
  });
}

export function persistLocale(locale: SupportedLocale): void {
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // Persistence is a convenience, not a requirement; the session keeps working.
  }
}

/** Apply the locale to the document so assistive tech and hyphenation follow it. */
export function applyDocumentLocale(locale: SupportedLocale): void {
  const root = document.documentElement;
  root.lang = locale;
  root.dir = directionFor(locale);
}
