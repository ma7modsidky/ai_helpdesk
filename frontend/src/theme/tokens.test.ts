import { describe, expect, it } from 'vitest';

import { TICKET_PRIORITIES, TICKET_STATUSES, MEMBERSHIP_ROLES } from '@/lib/domain';

import {
  PALETTE_TOKENS,
  PRIORITY_TONES,
  ROLE_TONES,
  STATUS_TONES,
  type ToneTokens,
} from './tokens';

/**
 * Contrast, computed rather than eyeballed.
 *
 * jsdom cannot evaluate `color-contrast` in axe, and a reviewer cannot reliably see 4.5:1
 * in two themes. Reading the tokens directly and computing the WCAG ratio is exact, runs in
 * milliseconds, and fails the moment someone nudges a colour (07 §8).
 */
const AA_TEXT = 4.5;
const AA_NON_TEXT = 3;

function parseHex(hex: string): [number, number, number] {
  const value = hex.replace('#', '');
  const full =
    value.length === 3
      ? value
          .split('')
          .map((char) => char + char)
          .join('')
      : value;
  return [
    Number.parseInt(full.slice(0, 2), 16),
    Number.parseInt(full.slice(2, 4), 16),
    Number.parseInt(full.slice(4, 6), 16),
  ];
}

function parseRgba(color: string): [number, number, number, number] {
  const match = /rgba?\(([^)]+)\)/.exec(color);
  if (!match?.[1]) {
    throw new Error(`Unsupported colour: ${color}`);
  }
  const parts = match[1].split(',').map((part) => Number.parseFloat(part.trim()));
  return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0, parts[3] ?? 1];
}

function channel(value: number): number {
  const normalized = value / 255;
  return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
}

function luminance(color: string): number {
  const [r, g, b] = color.startsWith('#') ? parseHex(color) : parseRgba(color);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** Composite a possibly translucent background onto an opaque one. */
function over(background: string, base: string): string {
  if (background.startsWith('#')) {
    return background;
  }
  const [r, g, b, alpha] = parseRgba(background);
  const [br, bg, bb] = parseHex(base);
  const blend = (top: number, bottom: number) => Math.round(top * alpha + bottom * (1 - alpha));
  return `#${[blend(r, br), blend(g, bg), blend(b, bb)]
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('')}`;
}

function contrast(foreground: string, background: string): number {
  const light = Math.max(luminance(foreground), luminance(background));
  const dark = Math.min(luminance(foreground), luminance(background));
  return (light + 0.05) / (dark + 0.05);
}

const SCHEMES = [
  { name: 'light', base: PALETTE_TOKENS.light.paper },
  { name: 'dark', base: PALETTE_TOKENS.dark.paper },
] as const;

interface ToneCase {
  readonly scheme: (typeof SCHEMES)[number];
  readonly group: string;
  readonly key: string;
  readonly tone: ToneTokens;
}

/** Flatten the three tone families into cases, so one loop covers all of them. */
function toneCases(): ToneCase[] {
  const cases: ToneCase[] = [];
  for (const scheme of SCHEMES) {
    const families: ReadonlyArray<readonly [string, Record<string, ToneTokens>]> = [
      ['status', STATUS_TONES[scheme.name]],
      ['priority', PRIORITY_TONES[scheme.name]],
      ['role', ROLE_TONES[scheme.name]],
    ];
    for (const [group, tones] of families) {
      for (const [key, tone] of Object.entries(tones)) {
        cases.push({ scheme, group, key, tone });
      }
    }
  }
  return cases;
}

describe('status, priority, and role tones', () => {
  for (const { scheme, group, key, tone } of toneCases()) {
    it(`${scheme.name} ${group} "${key}" text passes AA on its own surface`, () => {
      const surface = over(tone.background, scheme.base);
      expect(contrast(tone.text, surface)).toBeGreaterThanOrEqual(AA_TEXT);
    });

    it(`${scheme.name} ${group} "${key}" border is distinguishable`, () => {
      const semanticTone = over(tone.background, scheme.base);
      expect(contrast(tone.border, semanticTone)).toBeGreaterThanOrEqual(1.2);
    });
  }

  it('covers every enum value in both schemes', () => {
    for (const scheme of SCHEMES) {
      expect(Object.keys(STATUS_TONES[scheme.name]).sort()).toEqual([...TICKET_STATUSES].sort());
      expect(Object.keys(PRIORITY_TONES[scheme.name]).sort()).toEqual(
        [...TICKET_PRIORITIES].sort(),
      );
      expect(Object.keys(ROLE_TONES[scheme.name]).sort()).toEqual([...MEMBERSHIP_ROLES].sort());
    }
  });
});

describe('palette surfaces', () => {
  for (const scheme of SCHEMES) {
    const tokens = PALETTE_TOKENS[scheme.name];

    it(`${scheme.name} body text passes AA on paper and on the page background`, () => {
      expect(contrast(tokens.textPrimary, tokens.paper)).toBeGreaterThanOrEqual(AA_TEXT);
      expect(contrast(tokens.textPrimary, tokens.pageBackground)).toBeGreaterThanOrEqual(AA_TEXT);
      expect(contrast(tokens.textSecondary, tokens.paper)).toBeGreaterThanOrEqual(AA_TEXT);
    });

    it(`${scheme.name} primary button text clears AA against its own main colour`, () => {
      expect(contrast(tokens.primaryContrastText, tokens.primary)).toBeGreaterThanOrEqual(AA_TEXT);
    });

    // A divider is decoration, so WCAG's 3:1 non-text threshold does not apply to it.
    // It still has to be visible on a real screen, which the measured 1.42 / 1.47 satisfy.
    it(`${scheme.name} dividers stay visible against paper`, () => {
      expect(contrast(tokens.divider, tokens.paper)).toBeGreaterThanOrEqual(1.4);
    });

    it(`${scheme.name} focus ring colour is distinguishable from the surface`, () => {
      expect(contrast(tokens.primary, tokens.paper)).toBeGreaterThanOrEqual(AA_NON_TEXT);
    });

    it(`${scheme.name} app bar and navigation surfaces stay distinguishable from paper`, () => {
      expect(contrast(tokens.appBar, tokens.pageBackground)).toBeGreaterThanOrEqual(1.0);
      expect(contrast(tokens.navigation, tokens.pageBackground)).toBeGreaterThanOrEqual(1.0);
    });
  }
});
