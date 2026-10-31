/**
 * Status, priority, and role pills.
 *
 * Each pill has a light and a dark tone, and the dark one is applied through
 * `theme.applyStyles`, which compiles to the selector for the active colour scheme.
 * That keeps the decision inside CSS instead of asking JavaScript which scheme is
 * active, so a pill is correct on first paint and stays correct when the mode changes
 * without a re-render.
 */

import type { SxProps, Theme } from '@mui/material/styles';

import type { ToneTokens } from './tokens';

export function toneSx(light: ToneTokens, dark: ToneTokens): SxProps<Theme> {
  return (theme: Theme) => ({
    color: light.text,
    backgroundColor: light.background,
    border: `1px solid ${light.border}`,
    ...theme.applyStyles('dark', {
      color: dark.text,
      backgroundColor: dark.background,
      border: `1px solid ${dark.border}`,
    }),
  });
}
