import i18n, { type i18n as I18nInstance } from 'i18next';
import { initReactI18next } from 'react-i18next';

import ar from './locales/ar.json';
import en from './locales/en.json';
import { DEFAULT_LOCALE, resolveLocaleFromBrowser, type SupportedLocale } from './locale';

export const TRANSLATION_NAMESPACE = 'translation';

/**
 * Build an i18next instance.
 *
 * An explicit factory rather than the global singleton: tests render in both
 * languages, and a shared instance would leak the previous test's choice.
 * `initAsync: false` keeps the start synchronous because both catalogs are already in
 * memory, which is what lets the first render translate immediately.
 */
export function createI18nInstance(locale: SupportedLocale = resolveLocaleFromBrowser()) {
  const instance = i18n.createInstance();
  void instance.use(initReactI18next).init({
    resources: {
      en: { [TRANSLATION_NAMESPACE]: en },
      ar: { [TRANSLATION_NAMESPACE]: ar },
    },
    lng: locale,
    fallbackLng: DEFAULT_LOCALE,
    defaultNS: TRANSLATION_NAMESPACE,
    ns: [TRANSLATION_NAMESPACE],
    initAsync: false,
    // React escapes interpolated values itself; escaping here would double-encode
    // an Arabic name or a ticket subject containing an ampersand.
    interpolation: { escapeValue: false },
    returnNull: false,
    react: { useSuspense: false },
  });
  return instance;
}

export type AppI18n = I18nInstance;
