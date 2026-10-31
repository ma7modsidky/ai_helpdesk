import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';

/**
 * The product mark. Inline SVG rather than a file: it is a handful of paths, it inherits
 * the theme's primary colour, it needs no network request, and there is no asset
 * pipeline to maintain (07 §9).
 */
export function BrandMark({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, minWidth: 0 }}>
      <Box
        component="svg"
        viewBox="0 0 32 32"
        role="img"
        aria-hidden="true"
        sx={{ width: 28, height: 28, flexShrink: 0, color: 'primary.main' }}
      >
        <rect x="1" y="1" width="30" height="30" rx="8" fill="currentColor" />
        <path
          d="M9 21.5c0-1.1.9-2 2-2h4.2l4.3-3.2c.5-.4 1.2 0 1.2.6v6.3c0 1.1-.9 2-2 2H11c-1.1 0-2-.9-2-2Z"
          fill="#fff"
          fillOpacity="0.92"
        />
        <path
          d="M9.6 11.8c0-1 .8-1.8 1.8-1.8h9.2c1 0 1.8.8 1.8 1.8v2.4c0 1-.8 1.8-1.8 1.8h-9.2c-1 0-1.8-.8-1.8-1.8v-2.4Z"
          fill="#fff"
          fillOpacity="0.6"
        />
      </Box>
      {!compact && (
        <Typography
          component="span"
          variant="subtitle1"
          sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}
        >
          {t('common.appName')}
        </Typography>
      )}
    </Box>
  );
}
