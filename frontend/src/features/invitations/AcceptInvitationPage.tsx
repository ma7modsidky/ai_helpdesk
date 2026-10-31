import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { RoleChip } from '@/components/Chips';
import { LoadingPanel } from '@/components/StatePanel';
import { formatDateTime } from '@/i18n/formatters';
import { isSupportedLocale, type SupportedLocale } from '@/i18n/locale';
import { isApiError } from '@/lib/api/errors';

import { AuthLayout } from '@/features/auth/AuthLayout';
import { useSession } from '@/features/auth/useSession';

import { acceptInvitation, previewInvitation } from './api';
import type { InvitationState } from '@/lib/domain';

/**
 * `/invite/:token`.
 *
 * The invitee sees what they are joining before they act, and every state has its own
 * message: an expired or revoked invitation is never presented with a button that cannot
 * succeed. The invited address is not returned by the preview, so a mismatch can only be
 * discovered by attempting acceptance — which is why the 403 has its own explanation
 * rather than a generic failure (07 §6.2).
 */
export function AcceptInvitationPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { token = '' } = useParams<{ token: string }>();
  const session = useSession();

  const locale: SupportedLocale = isSupportedLocale(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : 'en';

  const preview = useQuery({
    queryKey: ['invitation-preview', token],
    queryFn: ({ signal }) => previewInvitation(token, signal),
    retry: false,
    staleTime: 0,
  });

  const accept = useMutation({
    mutationFn: () => acceptInvitation(token),
    onSuccess: (result) => {
      void navigate(`/app/${result.workspace.id}/inbox`, { replace: true });
    },
  });

  const inviteState: InvitationState | null = preview.data?.status ?? null;
  const wrongAccount =
    accept.isError &&
    isApiError(accept.error) &&
    accept.error.kind === 'forbidden' &&
    session.data !== null;

  const signInPath = `/login?next=${encodeURIComponent(`/invite/${token}`)}`;
  const registerPath = `/register?next=${encodeURIComponent(`/invite/${token}`)}`;

  if (preview.isPending) {
    return (
      <AuthLayout title={t('invitations.title')}>
        <LoadingPanel />
      </AuthLayout>
    );
  }

  if (preview.isError) {
    const notFound = isApiError(preview.error) && preview.error.kind === 'notFound';
    return (
      <AuthLayout title={t('invitations.title')}>
        <Stack spacing={2}>
          <Alert severity="warning">
            {notFound ? t('invitations.invalid.notFound') : t('invitations.invalid.title')}
          </Alert>
          <Button variant="contained" href="/app/workspaces">
            {t('workspaces.backToPicker')}
          </Button>
        </Stack>
      </AuthLayout>
    );
  }

  const { workspace_name: workspaceName, role, expires_at: expiresAt } = preview.data;

  return (
    <AuthLayout title={t('invitations.title')}>
      <Stack spacing={2}>
        <Typography variant="body1">
          {t('invitations.offer', {
            workspace: workspaceName,
            role: t(`enums.role.${role}`),
          })}
        </Typography>

        <Stack
          direction="row"
          spacing={1}
          useFlexGap
          sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}
        >
          <RoleChip role={role} />
          <Typography variant="caption" color="text.secondary">
            {formatDateTime(expiresAt, locale)}
          </Typography>
        </Stack>

        {inviteState !== 'pending' && (
          <Alert severity={inviteState === 'accepted' ? 'info' : 'warning'}>
            {t(`invitations.invalid.${inviteState}`)}
          </Alert>
        )}

        {wrongAccount && session.data && (
          <Alert severity="warning">
            {t('invitations.wrongAccount', { email: session.data.email })}
          </Alert>
        )}

        {accept.isError && !wrongAccount && (
          <Alert severity="error">
            {isApiError(accept.error) && accept.error.code === 'invitation_expired'
              ? t('invitations.invalid.expired')
              : t('errors.unexpected')}
          </Alert>
        )}

        {session.data === null && (
          <>
            <Typography variant="body2" color="text.secondary">
              {t('invitations.requiresSignIn')}
            </Typography>
            <Stack direction="row" spacing={1}>
              <Button variant="contained" href={signInPath}>
                {t('auth.signIn.submit')}
              </Button>
              <Button variant="outlined" href={registerPath}>
                {t('auth.signIn.createAccount')}
              </Button>
            </Stack>
          </>
        )}

        {session.data !== null && (
          <Stack direction="row" spacing={1}>
            {inviteState === 'pending' && (
              <Button
                variant="contained"
                onClick={() => accept.mutate()}
                disabled={accept.isPending}
              >
                {accept.isPending ? t('invitations.accepting') : t('invitations.accept')}
              </Button>
            )}
            {wrongAccount && (
              <Button variant="outlined" href={signInPath}>
                {t('invitations.switchAccount')}
              </Button>
            )}
          </Stack>
        )}
      </Stack>
    </AuthLayout>
  );
}
