/**
 * Component defaults (07 §2.4).
 *
 * These exist so a screen writes `<Button variant="contained">` and gets the product's
 * button, instead of every screen restating radius, weight, elevation, and casing. Anything
 * only one screen needs belongs in that screen, not here.
 */

import type { ThemeOptions } from '@mui/material/styles';

export const componentOverrides: ThemeOptions['components'] = {
  MuiCssBaseline: {
    styleOverrides: (theme) => ({
      body: {
        WebkitFontSmoothing: 'antialiased',
        MozOsxFontSmoothing: 'grayscale',
      },
      // A visible focus ring on everything focusable. Inputs are excluded because MUI
      // already draws an unambiguous primary border and ring on those, and doubling it
      // looks like a rendering fault.
      '*:focus-visible': {
        outline: `2px solid ${theme.palette.primary.main}`,
        outlineOffset: 2,
      },
      '.MuiInputBase-input:focus-visible, .MuiOutlinedInput-input:focus-visible': {
        outline: 'none',
      },
    }),
  },
  MuiButton: {
    defaultProps: { disableElevation: true },
    styleOverrides: {
      root: {
        textTransform: 'none',
        fontWeight: 600,
        borderRadius: 8,
      },
    },
  },
  MuiTextField: {
    defaultProps: { size: 'small' },
  },
  MuiSelect: {
    defaultProps: { size: 'small' },
  },
  MuiPaper: {
    styleOverrides: {
      // MUI paints a gradient over dark surfaces by default; this app separates
      // surfaces with borders and a single background tone instead.
      root: { backgroundImage: 'none' },
    },
  },
  MuiCard: {
    styleOverrides: {
      root: ({ theme }) => ({
        border: `1px solid ${theme.palette.divider}`,
        boxShadow: 'none',
      }),
    },
  },
  MuiAppBar: {
    defaultProps: { color: 'default', elevation: 0 },
    styleOverrides: {
      root: ({ theme }) => ({
        backgroundColor: theme.palette.background.paper,
        borderBottom: `1px solid ${theme.palette.divider}`,
      }),
    },
  },
  MuiDrawer: {
    styleOverrides: {
      paper: ({ theme }) => ({
        borderInlineEnd: `1px solid ${theme.palette.divider}`,
      }),
    },
  },
  MuiChip: {
    styleOverrides: {
      root: { fontWeight: 600, borderRadius: 6 },
    },
  },
  MuiListItemButton: {
    styleOverrides: {
      root: { borderRadius: 8 },
    },
  },
  MuiDialog: {
    styleOverrides: {
      paper: { borderRadius: 12 },
    },
  },
  MuiAlert: {
    styleOverrides: {
      root: { alignItems: 'center', borderRadius: 8 },
    },
  },
  MuiSkeleton: {
    defaultProps: { animation: 'wave' },
  },
  MuiTooltip: {
    defaultProps: { arrow: true },
  },
  MuiTab: {
    styleOverrides: {
      root: { textTransform: 'none', fontWeight: 600, minHeight: 44 },
    },
  },
};
