import AddIcon from '@mui/icons-material/Add';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { AppLanguageToggle } from '@/components/AppLanguageToggle';
import { AppThemeToggle } from '@/components/AppThemeToggle';
import { BrandMark } from '@/components/BrandMark';
import { DirectionalIcon } from '@/components/DirectionalIcon';
import { EmptyPanel, ErrorPanel, ListSkeleton } from '@/components/StatePanel';
import { formatDate } from '@/i18n/formatters';
import { isSupportedLocale, type SupportedLocale } from '@/i18n/locale';
import { useLogout, useSession } from '@/features/auth/useSession';

import { CreateWorkspaceDialog } from './CreateWorkspaceDialog';
import { useWorkspaces } from './queries';

/**
 * The landing screen after sign-in: every workspace the account belongs to, or an empty
 * state that explains the two ways to get one (create, or accept an invitation).
 */
export function WorkspacePickerPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const session = useSession();
  const logout = useLogout();
  const workspaces = useWorkspaces();
  const [createOpen, setCreateOpen] = useState(false);

  const locale: SupportedLocale = isSupportedLocale(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : 'en';

  const openWorkspace = (workspaceId: string) => {
    void navigate(`/app/${workspaceId}/inbox`);
  };

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
        sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', p: 2 }}
      >
        <BrandMark />
        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
          <AppLanguageToggle />
          <AppThemeToggle />
          <Button size="small" color="inherit" onClick={() => logout.mutate()}>
            {t('common.actions.signOut')}
          </Button>
        </Stack>
      </Box>

      <Box component="main" sx={{ flex: 1, width: '100%', maxWidth: 720, mx: 'auto', p: 2 }}>
        <Stack spacing={0.5} sx={{ mb: 3 }}>
          <Typography component="h1" variant="h5">
            {t('workspaces.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('workspaces.subtitle')}
          </Typography>
          {session.data && (
            <Typography variant="caption" color="text.secondary">
              {t('auth.signedInAs', { email: session.data.email })}
            </Typography>
          )}
        </Stack>

        <Stack spacing={2}>
          {workspaces.isPending && <ListSkeleton rows={3} />}

          {workspaces.isError && (
            <ErrorPanel error={workspaces.error} onRetry={() => void workspaces.refetch()} />
          )}

          {workspaces.data && workspaces.data.length === 0 && (
            <EmptyPanel
              title={t('workspaces.empty.title')}
              description={t('workspaces.empty.description')}
              action={
                <Button
                  variant="contained"
                  startIcon={<AddIcon />}
                  onClick={() => setCreateOpen(true)}
                >
                  {t('workspaces.create')}
                </Button>
              }
            />
          )}

          {workspaces.data && workspaces.data.length > 0 && (
            <Stack spacing={1.5}>
              <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
                <Button startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
                  {t('workspaces.create')}
                </Button>
              </Stack>
              {workspaces.data.map((workspace) => (
                <Paper key={workspace.id} variant="outlined" sx={{ p: 0 }}>
                  <Button
                    onClick={() => openWorkspace(workspace.id)}
                    fullWidth
                    color="inherit"
                    sx={{
                      justifyContent: 'space-between',
                      textAlign: 'start',
                      p: 2,
                      borderRadius: 2,
                    }}
                  >
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="subtitle1" component="span" noWrap>
                        {workspace.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {workspace.slug} · {formatDate(workspace.created_at, locale)}
                      </Typography>
                    </Box>
                    <DirectionalIcon
                      icon={ChevronRightIcon}
                      aria-hidden="true"
                      sx={{ color: 'text.secondary' }}
                    />
                  </Button>
                </Paper>
              ))}
            </Stack>
          )}
        </Stack>

        {/* Mounted only while open: every opening starts from an empty form, with no state
          to reset and no effect to run. */}
        {createOpen && (
          <CreateWorkspaceDialog
            onClose={() => setCreateOpen(false)}
            onCreated={(workspace) => openWorkspace(workspace.id)}
          />
        )}
      </Box>
    </Box>
  );
}
