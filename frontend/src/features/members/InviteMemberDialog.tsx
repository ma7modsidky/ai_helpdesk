import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { useApiFormErrors } from '@/components/useApiFormSubmit';
import { INVITABLE_ROLES, type MembershipRole } from '@/lib/domain';

import { useInviteMember } from './queries';
import type { InvitationWithLink } from './api';

/** The role an invitation starts on; every role in the list is one the server accepts. */
const DEFAULT_INVITE_ROLE: MembershipRole = 'agent';

/**
 * Invite one person to the workspace.
 *
 * The offered roles are the contract's invitable set — ownership is not grantable through
 * an invitation — and the field errors are the server's, so a duplicate pending invitation
 * or an address that is already a member is explained rather than predicted.
 */
export function InviteMemberDialog({
  workspaceId,
  onInvited,
  onClose,
}: {
  workspaceId: string;
  onInvited: (invitation: InvitationWithLink) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const invite = useInviteMember(workspaceId);
  const { fieldErrors, formError, applyError, reset } = useApiFormErrors();

  const [email, setEmail] = useState('');
  const [role, setRole] = useState<MembershipRole>(DEFAULT_INVITE_ROLE);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reset();
    invite.mutate({ email: email.trim(), role }, { onSuccess: onInvited, onError: applyError });
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <form onSubmit={submit} noValidate>
        <DialogTitle>{t('members.invite.title')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            <DialogContentText>{t('members.invite.description')}</DialogContentText>
            {formError && <Alert severity="error">{t(formError)}</Alert>}
            <TextField
              id="invite-email"
              label={t('members.invite.fields.email')}
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              error={fieldErrors['email'] !== undefined}
              helperText={fieldErrors['email']}
              autoFocus
              required
              fullWidth
            />
            <TextField
              id="invite-role"
              select
              label={t('members.invite.fields.role')}
              value={role}
              onChange={(event) => setRole(event.target.value as MembershipRole)}
              error={fieldErrors['role'] !== undefined}
              helperText={fieldErrors['role']}
              required
              fullWidth
            >
              {INVITABLE_ROLES.map((value) => (
                <MenuItem key={value} value={value}>
                  {t(`enums.role.${value}`)}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose} color="inherit">
            {t('common.actions.cancel')}
          </Button>
          <Button type="submit" variant="contained" disabled={invite.isPending}>
            {invite.isPending ? t('common.loading') : t('members.invite.submit')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
