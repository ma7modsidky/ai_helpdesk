import CheckIcon from '@mui/icons-material/Check';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import IconButton from '@mui/material/IconButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Tooltip from '@mui/material/Tooltip';
import { useColorScheme, useTheme } from '@mui/material/styles';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

const MODES = ['system', 'light', 'dark'] as const;
type Mode = (typeof MODES)[number];

/**
 * System, light, or dark — three choices rather than a two-way switch, because "follow my
 * OS" is a real preference and a toggle cannot express it. MUI persists the selection
 * under `mui-mode` and applies it across tabs; `index.html` reads the same key before the
 * bundle runs, which is what prevents a flash of the wrong theme.
 */
export function AppThemeToggle() {
  const { t } = useTranslation();
  const { mode, setMode } = useColorScheme();
  const theme = useTheme();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const active: Mode = MODES.find((candidate) => candidate === mode) ?? 'system';
  const endEdge = theme.direction === 'rtl' ? 'left' : 'right';

  return (
    <>
      <Tooltip title={t('a11y.themeMenu')}>
        <IconButton
          onClick={(event) => setAnchor(event.currentTarget)}
          aria-label={t('a11y.themeMenu')}
          aria-haspopup="menu"
          aria-expanded={anchor !== null}
          size="small"
        >
          <DarkModeOutlinedIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Menu
        anchorEl={anchor}
        open={anchor !== null}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: endEdge }}
        transformOrigin={{ vertical: 'top', horizontal: endEdge }}
      >
        {MODES.map((candidate) => (
          <MenuItem
            key={candidate}
            selected={candidate === active}
            onClick={() => {
              setAnchor(null);
              setMode(candidate);
            }}
          >
            <ListItemIcon sx={{ minWidth: 32 }}>
              {candidate === active && <CheckIcon fontSize="small" />}
            </ListItemIcon>
            <ListItemText>{t(`common.theme.${candidate}`)}</ListItemText>
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
