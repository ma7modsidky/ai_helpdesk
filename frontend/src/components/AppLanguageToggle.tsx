import CheckIcon from '@mui/icons-material/Check';
import LanguageIcon from '@mui/icons-material/Language';
import IconButton from '@mui/material/IconButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Tooltip from '@mui/material/Tooltip';
import { useTheme } from '@mui/material/styles';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  isSupportedLocale,
  persistLocale,
  SUPPORTED_LOCALES,
  type SupportedLocale,
} from '@/i18n/locale';

/**
 * Switching language is a runtime action, not a reload: i18next changes the translated
 * strings, the theme provider rebuilds with the new direction, and the Emotion cache
 * swaps so physical CSS is flipped (ADR-031). The choice is persisted client-side.
 */
export function AppLanguageToggle() {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  // MUI does not mirror anchor origins, so the edge is chosen from the direction:
  // "end" means the right edge in LTR and the left edge in RTL.
  const endEdge = theme.direction === 'rtl' ? 'left' : 'right';
  const active: SupportedLocale = isSupportedLocale(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : 'en';

  const select = (locale: SupportedLocale) => {
    setAnchor(null);
    persistLocale(locale);
    void i18n.changeLanguage(locale);
  };

  return (
    <>
      <Tooltip title={t('a11y.languageMenu')}>
        <IconButton
          onClick={(event) => setAnchor(event.currentTarget)}
          aria-label={t('a11y.languageMenu')}
          aria-haspopup="menu"
          aria-expanded={anchor !== null}
          size="small"
        >
          <LanguageIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Menu
        anchorEl={anchor}
        open={anchor !== null}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: endEdge }}
        transformOrigin={{ vertical: 'top', horizontal: endEdge }}
      >
        {SUPPORTED_LOCALES.map((locale) => (
          <MenuItem
            key={locale}
            selected={locale === active}
            onClick={() => select(locale)}
            // Both catalogs carry the two endonyms unchanged, so a language always
            // reads as itself whichever locale is active.
            lang={locale}
          >
            <ListItemIcon sx={{ minWidth: 32 }}>
              {locale === active && <CheckIcon fontSize="small" />}
            </ListItemIcon>
            <ListItemText>{t(`common.language.${locale}`)}</ListItemText>
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
