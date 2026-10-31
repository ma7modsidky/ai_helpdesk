import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { StatePanel } from '@/components/StatePanel';

/** The `*` route: a wrong URL gets an explanation and a way back, not a blank page. */
export function NotFoundPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Box sx={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', p: 2 }}>
      <Stack sx={{ width: '100%', maxWidth: 480 }}>
        <StatePanel
          icon={null}
          title={t('errors.notFound')}
          action={
            <Button variant="contained" onClick={() => void navigate('/app/workspaces')}>
              {t('workspaces.backToPicker')}
            </Button>
          }
        />
      </Stack>
    </Box>
  );
}
