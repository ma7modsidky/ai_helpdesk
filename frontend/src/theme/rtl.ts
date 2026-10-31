/**
 * Emotion caches for both directions (ADR-031).
 *
 * `theme.direction` alone drives MUI's own component internals (drawer anchor, tabs
 * scrolling, autocomplete placement), but the CSS those components generate still
 * carries physical properties such as `padding-left`. The stylis RTL plugin rewrites
 * them at insertion time, and it needs its own cache, because a cache's plugin list is
 * fixed at creation. Switching direction therefore means switching caches.
 *
 * `prefixer` from stylis is listed explicitly on both caches: passing `stylisPlugins`
 * replaces Emotion's defaults, which are exactly `[prefixer]`, so omitting it on the
 * LTR cache would silently drop vendor prefixes there.
 */

import createCache from '@emotion/cache';
import type { EmotionCache } from '@emotion/react';
import rtlPlugin from '@mui/stylis-plugin-rtl';
import { prefixer } from 'stylis';

import type { Direction } from '@/i18n/locale';

export const ltrCache: EmotionCache = createCache({
  key: 'resolveai-ltr',
  stylisPlugins: [prefixer],
});

export const rtlCache: EmotionCache = createCache({
  key: 'resolveai-rtl',
  stylisPlugins: [prefixer, rtlPlugin],
});

export function cacheForDirection(direction: Direction): EmotionCache {
  return direction === 'rtl' ? rtlCache : ltrCache;
}
