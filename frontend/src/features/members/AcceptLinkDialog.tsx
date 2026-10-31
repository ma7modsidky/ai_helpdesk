import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { MembershipRole } from '@/lib/domain';

/**
 * The one moment an invitation link is visible.
 *
 * The API returns `accept_path` only from create and resend, so this dialog exists to hand
 * it to the inviter immediately; nothing else in the app can display it, and it is not
 * cached anywhere (ADR-026).
 */
export function AcceptLinkDialog({
  acceptPath,
  role,
  onClose,
}: {
  acceptPath: string;
  role: MembershipRole;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const fullUrl = `${window.location.origin}${acceptPath}`;

  const copy = () => {
    // The clipboard API is unavailable on plain HTTP in some browsers; the link stays on
    // screen either way, so a failed copy never hides it.
    void navigator.clipboard
      ?.writeText(fullUrl)
      .then(() => setCopied(true))
      .catch(() => setCopied(false));
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>{t('members.invite.linkTitle')}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          {t('members.invite.linkDescription', { role: t(`enums.role.${role}`) })}
        </DialogContentText>
        <Typography variant="body2" sx={{ wordBreak: 'break-all', fontFamily: 'monospace' }}>
          {acceptPath}
        </Typography>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={copy}>
          {copied ? t('common.actions.copied') : t('common.actions.copy')}
        </Button>
        <Button variant="contained" onClick={onClose} autoFocus>
          {t('common.actions.done')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
