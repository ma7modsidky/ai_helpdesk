/**
 * The design tokens (07 §2.1).
 *
 * Light and dark are declared together, so a colour that only works in one mode is
 * visible as a gap in this file rather than as a bug in a screenshot. Components read
 * these through the theme — a hardcoded colour in a component is a review finding.
 *
 * Every text-on-surface pair below is asserted by `tokens.test.ts` against the WCAG
 * 2.2 AA thresholds, which is what makes the contrast claim checkable instead of
 * something a reviewer has to eyeball in two themes.
 */

import type { ColorSystemOptions } from '@mui/material/styles';

import type { MembershipRole, TicketPriority, TicketStatus } from '@/lib/domain';

export type ColorScheme = 'light' | 'dark';

/** A status pill: readable text, a tinted surface, and a matching border. */
export interface ToneTokens {
  readonly text: string;
  readonly background: string;
  readonly border: string;
}

const LIGHT_STATUS: Record<TicketStatus, ToneTokens> = {
  open: { text: '#123F9E', background: '#E7EDFD', border: '#C6D5FA' },
  in_progress: { text: '#8A4A00', background: '#FDF0DC', border: '#F5D9AE' },
  waiting_on_customer: { text: '#0B5D57', background: '#DFF3F0', border: '#B4E0D9' },
  resolved: { text: '#12603C', background: '#E1F4E9', border: '#B7E2C8' },
  closed: { text: '#444C5A', background: '#EDEFF2', border: '#D3D8DF' },
};

const DARK_STATUS: Record<TicketStatus, ToneTokens> = {
  open: { text: '#A8C0FF', background: 'rgba(31, 79, 216, 0.22)', border: '#3D548F' },
  in_progress: { text: '#F0C27A', background: 'rgba(178, 94, 0, 0.20)', border: '#7A5A2A' },
  waiting_on_customer: {
    text: '#7FD8CC',
    background: 'rgba(11, 93, 87, 0.25)',
    border: '#2E6B65',
  },
  resolved: { text: '#8FDDAC', background: 'rgba(18, 96, 60, 0.24)', border: '#2F6B49' },
  closed: { text: '#B6BECB', background: 'rgba(120, 130, 145, 0.20)', border: '#4A5260' },
};

const LIGHT_PRIORITY: Record<TicketPriority, ToneTokens> = {
  low: { text: '#444C5A', background: '#EDEFF2', border: '#D3D8DF' },
  normal: { text: '#123F9E', background: '#E7EDFD', border: '#C6D5FA' },
  high: { text: '#8F4600', background: '#FCE8D8', border: '#F3C9A8' },
  urgent: { text: '#9E1B1B', background: '#FCE4E4', border: '#F3BDBD' },
};

const DARK_PRIORITY: Record<TicketPriority, ToneTokens> = {
  low: { text: '#B6BECB', background: 'rgba(120, 130, 145, 0.20)', border: '#4A5260' },
  normal: { text: '#A8C0FF', background: 'rgba(31, 79, 216, 0.22)', border: '#3D548F' },
  high: { text: '#F3B27A', background: 'rgba(178, 94, 0, 0.22)', border: '#7A5228' },
  urgent: { text: '#FFA9A9', background: 'rgba(192, 40, 31, 0.22)', border: '#8D3A34' },
};

/**
 * Role colours are neutral by design: role matters for what a control allows, and a
 * colourful badge would compete with the ticket status that carries operational meaning.
 */
const LIGHT_ROLE: Record<MembershipRole, ToneTokens> = {
  owner: { text: '#3B2A78', background: '#EDE9FB', border: '#D2C8F3' },
  admin: { text: '#123F9E', background: '#E7EDFD', border: '#C6D5FA' },
  manager: { text: '#0B5D57', background: '#DFF3F0', border: '#B4E0D9' },
  agent: { text: '#444C5A', background: '#EDEFF2', border: '#D3D8DF' },
};

const DARK_ROLE: Record<MembershipRole, ToneTokens> = {
  owner: { text: '#C3B4FF', background: 'rgba(101, 75, 205, 0.24)', border: '#584A96' },
  admin: { text: '#A8C0FF', background: 'rgba(31, 79, 216, 0.22)', border: '#3D548F' },
  manager: { text: '#7FD8CC', background: 'rgba(11, 93, 87, 0.25)', border: '#2E6B65' },
  agent: { text: '#B6BECB', background: 'rgba(120, 130, 145, 0.20)', border: '#4A5260' },
};

export const STATUS_TONES: Record<ColorScheme, Record<TicketStatus, ToneTokens>> = {
  light: LIGHT_STATUS,
  dark: DARK_STATUS,
};

export const PRIORITY_TONES: Record<ColorScheme, Record<TicketPriority, ToneTokens>> = {
  light: LIGHT_PRIORITY,
  dark: DARK_PRIORITY,
};

export const ROLE_TONES: Record<ColorScheme, Record<MembershipRole, ToneTokens>> = {
  light: LIGHT_ROLE,
  dark: DARK_ROLE,
};

/**
 * The named colours each scheme must provide.
 *
 * Declared as a flat record rather than inline inside `palette` so the contrast test can
 * read the exact same values the theme uses, instead of reaching into MUI's option types
 * and comparing a value that might not be the one in effect.
 */
export interface PaletteTokens {
  readonly primary: string;
  readonly primaryContrastText: string;
  readonly secondary: string;
  readonly pageBackground: string;
  readonly paper: string;
  readonly appBar: string;
  readonly navigation: string;
  readonly textPrimary: string;
  readonly textSecondary: string;
  readonly divider: string;
  readonly success: string;
  readonly warning: string;
  readonly error: string;
}

export const PALETTE_TOKENS: Record<ColorScheme, PaletteTokens> = {
  light: {
    primary: '#1F4FD8',
    primaryContrastText: '#FFFFFF',
    secondary: '#5B6473',
    pageBackground: '#F4F6F8',
    paper: '#FFFFFF',
    appBar: '#FFFFFF',
    navigation: '#FFFFFF',
    textPrimary: '#101828',
    textSecondary: '#5C6472',
    divider: '#D3D9E1',
    success: '#16794C',
    warning: '#B25E00',
    error: '#C0281F',
  },
  dark: {
    primary: '#93B4FF',
    primaryContrastText: '#0B1B3D',
    secondary: '#AEB6C4',
    pageBackground: '#0F1318',
    paper: '#171B22',
    appBar: '#171B22',
    navigation: '#141821',
    textPrimary: '#E8EBF0',
    textSecondary: '#A3ACBB',
    divider: '#313845',
    success: '#5FD08D',
    warning: '#E1A75C',
    error: '#F08C86',
  },
};

/**
 * Build one colour scheme. Only the roles that differ between schemes are stated; MUI
 * derives the hover and active variants from `main`, which keeps each scheme internally
 * consistent rather than relying on two hand-maintained values staying in step.
 */
function buildScheme(tokens: PaletteTokens): ColorSystemOptions {
  return {
    palette: {
      primary: { main: tokens.primary, contrastText: tokens.primaryContrastText },
      secondary: { main: tokens.secondary },
      background: { default: tokens.pageBackground, paper: tokens.paper },
      text: { primary: tokens.textPrimary, secondary: tokens.textSecondary },
      divider: tokens.divider,
      success: { main: tokens.success },
      warning: { main: tokens.warning },
      error: { main: tokens.error },
      info: { main: tokens.primary },
    },
  };
}

export const LIGHT_SCHEME: ColorSystemOptions = buildScheme(PALETTE_TOKENS.light);
export const DARK_SCHEME: ColorSystemOptions = buildScheme(PALETTE_TOKENS.dark);
