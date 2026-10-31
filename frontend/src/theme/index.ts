/**
 * The application theme (07 §2 and §4).
 *
 * One function builds the theme for a direction and a locale, so the two things that
 * vary at runtime are inputs rather than patches. Colour schemes are declared together
 * through MUI's `colorSchemes`, which is what makes the mode switch a CSS-variable swap
 * instead of a re-render of the tree.
 */

import { createTheme, type Theme } from '@mui/material/styles';
import type { ThemeOptions } from '@mui/material/styles';

import type { Direction, SupportedLocale } from '@/i18n/locale';
import { componentOverrides } from './components';
import { DARK_SCHEME, LIGHT_SCHEME } from './tokens';

/**
 * Latin first, Arabic second. The two scripts are disjoint, so the browser picks the
 * right face per glyph and mixed content (an Arabic subject containing a Latin email
 * address) renders correctly without per-element font logic.
 */
export const FONT_STACK = [
  '"Inter Variable"',
  '"Noto Sans Arabic Variable"',
  'system-ui',
  '-apple-system',
  '"Segoe UI"',
  'Roboto',
  '"Helvetica Neue"',
  'Arial',
  'sans-serif',
].join(', ');

const BASE_TYPOGRAPHY: ThemeOptions['typography'] = {
  fontFamily: FONT_STACK,
  fontSize: 14,
  h4: { fontSize: '1.5rem', fontWeight: 600, lineHeight: 1.3, letterSpacing: 0 },
  h5: { fontSize: '1.25rem', fontWeight: 600, lineHeight: 1.35, letterSpacing: 0 },
  h6: { fontSize: '1.0625rem', fontWeight: 600, lineHeight: 1.4, letterSpacing: 0 },
  subtitle1: { fontSize: '1rem', fontWeight: 600 },
  subtitle2: { fontSize: '0.875rem', fontWeight: 600 },
  body1: { fontSize: '0.9375rem' },
  body2: { fontSize: '0.875rem' },
  button: { fontSize: '0.875rem', fontWeight: 600 },
  caption: { fontSize: '0.8125rem' },
};

/**
 * Arabic needs more vertical room than Latin at the same size: ascenders, descenders and
 * the marks above and below the baseline collide at a Latin line height, and letter
 * spacing (which MUI applies to buttons and overlines) is a Latin typographic device that
 * actively harms connected Arabic script. The base size also moves up a point because
 * Arabic reads smaller at an equal pixel size. Applied as a theme rule so no component
 * has to know about it (07 §2.2).
 */
const ARABIC_TYPOGRAPHY: ThemeOptions['typography'] = {
  fontSize: 15,
  h4: { lineHeight: 1.5 },
  h5: { lineHeight: 1.5 },
  h6: { lineHeight: 1.55, letterSpacing: 0 },
  subtitle1: { lineHeight: 1.7, letterSpacing: 0 },
  subtitle2: { lineHeight: 1.7, letterSpacing: 0 },
  body1: { lineHeight: 1.85, letterSpacing: 0 },
  body2: { lineHeight: 1.85, letterSpacing: 0 },
  button: { lineHeight: 1.75, letterSpacing: 0 },
  caption: { lineHeight: 1.75, letterSpacing: 0 },
  overline: { letterSpacing: 0, textTransform: 'none' },
};

export interface CreateAppThemeOptions {
  readonly direction: Direction;
  readonly locale: SupportedLocale;
}

export function createAppTheme({ direction, locale }: CreateAppThemeOptions): Theme {
  return createTheme({
    direction,
    colorSchemes: { light: LIGHT_SCHEME, dark: DARK_SCHEME },
    shape: { borderRadius: 8 },
    typography: {
      ...BASE_TYPOGRAPHY,
      ...(locale === 'ar' ? ARABIC_TYPOGRAPHY : {}),
    },
    components: componentOverrides,
  });
}
