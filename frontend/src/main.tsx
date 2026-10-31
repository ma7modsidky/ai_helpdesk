// Self-hosted variable fonts, imported here rather than fetched from a CDN: the app makes
// no third-party request at runtime, development and CI work offline, and the Arabic face
// is guaranteed to be present when the layout depends on it (07 §2.2).
import '@fontsource-variable/inter/index.css';
import '@fontsource-variable/noto-sans-arabic/index.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from '@/app/App';
import { createI18nInstance } from '@/i18n';
import { persistLocale, resolveLocaleFromBrowser } from '@/i18n/locale';
import { createQueryClient } from '@/lib/api/queryClient';

const container = document.getElementById('root');
if (!container) {
  throw new Error('The #root container is missing from index.html.');
}

// Resolve once, then remember it: a `?lang=` link (an invitation, a shared URL) has to
// survive the next in-app navigation, or an invitee who arrives in Arabic is handed back
// to English by the sign-up link on the page they landed on.
const locale = resolveLocaleFromBrowser();
persistLocale(locale);

createRoot(container).render(
  <StrictMode>
    <App i18n={createI18nInstance(locale)} queryClient={createQueryClient()} />
  </StrictMode>,
);
