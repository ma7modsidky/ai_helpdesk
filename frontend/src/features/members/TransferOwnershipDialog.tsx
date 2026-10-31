import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/lib/api/errors';

import { useTransferOwnership } from './queries';
import type { Member } from './api';

/**
 * Hand the workspace to another member, with the consequence stated before it happens.
 *
 * Transfer is one atomic operation (ADR-028), so there is no role picker here: the dialog
 * names the member, says that the caller becomes an admin, and requires a deliberate
 * confirmation. A refusal — a target that is no longer active — is shown, not hidden.
 */
export function TransferOwnershipDialog({
  workspaceId,
  member,
  onClose,
}: {
  workspaceId: string;
  member: Member;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const transfer = useTransferOwnership(workspaceId);
  const [refusal, setRefusal] = useState<string | null>(null);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setRefusal(null);
    transfer.mutate(member.id, {
      onSuccess: onClose,
      onError: (error) =>
        setRefusal(
          isApiError(error) && error.status === 409
            ? 'members.refusals.targetInactive'
            : 'errors.unexpected',
        ),
    });
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <form onSubmit={submit} noValidate>
        <DialogTitle>{t('members.transfer.title')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            {t('members.transfer.description', { email: member.email })}
          </DialogContentText>
          {refusal && <Alert severity="warning">{t(refusal)}</Alert>}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose} color="inherit">
            {t('common.actions.cancel')}
          </Button>
          <Button type="submit" variant="contained" disabled={transfer.isPending}>
            {transfer.isPending ? t('common.loading') : t('members.transfer.submit')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
