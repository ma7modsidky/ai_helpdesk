import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { AppLanguageToggle } from '@/components/AppLanguageToggle';
import { AppThemeToggle } from '@/components/AppThemeToggle';
import { BrandMark } from '@/components/BrandMark';

/**
 * The frame shared by sign-in, sign-up, and invitation acceptance: one centred column,
 * the brand, and the language and theme controls in reach — a first-time visitor needs
 * both before they can comfortably read anything else (07 §6.1).
 */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
  notice,
}: {
  title: string;
  subtitle?: string | undefined;
  children: ReactNode;
  footer?: ReactNode | undefined;
  notice?: string | undefined;
}) {
  const { t } = useTranslation();

  return (
    <Box
      sx={{
        minHeight: '100dvh',
        bgcolor: 'background.default',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Box
        component="header"
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 2,
          p: 2,
        }}
      >
        <BrandMark />
        <Stack direction="row" spacing={0.5}>
          <AppLanguageToggle />
          <AppThemeToggle />
        </Stack>
      </Box>

      <Box
        component="main"
        sx={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          px: 2,
          pb: 6,
        }}
      >
        <Paper variant="outlined" sx={{ width: '100%', maxWidth: 420, p: { xs: 2.5, sm: 3.5 } }}>
          <Stack spacing={2.5}>
            <Stack spacing={0.5}>
              <Typography component="h1" variant="h5">
                {title}
              </Typography>
              {subtitle && (
                <Typography variant="body2" color="text.secondary">
                  {subtitle}
                </Typography>
              )}
            </Stack>

            {notice && <Alert severity="info">{notice}</Alert>}

            {children}

            {footer && (
              <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.5 }}>{footer}</Box>
            )}
          </Stack>
        </Paper>
      </Box>

      <Box component="footer" sx={{ p: 2, textAlign: 'center' }}>
        <Typography variant="caption" color="text.secondary">
          {t('common.appName')}
        </Typography>
      </Box>
    </Box>
  );
}
