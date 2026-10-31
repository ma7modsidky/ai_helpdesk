import ForumOutlinedIcon from '@mui/icons-material/ForumOutlined';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { errorMessageKey } from '@/lib/api/errors';
import { MESSAGE_VISIBILITIES, type MessageVisibility } from '@/lib/domain';

import { useAddMessage } from './queries';

/**
 * Write a reply or a note (07 §6.6).
 *
 * The visibility starts unset on purpose: a composer that preselects `public_reply` sends a
 * customer-facing message the first time someone writes what they meant as an internal
 * note, so the mode is a deliberate choice and the send button stays disabled until it is
 * made. The text itself lives here, not in the parent, so a ticket refetch — including the
 * one the conflict prompt triggers — cannot discard unsent writing.
 */
export function TicketComposer({
  workspaceId,
  ticketId,
}: {
  workspaceId: string;
  ticketId: string;
}) {
  const { t } = useTranslation();
  const addMessage = useAddMessage(workspaceId, ticketId);

  const [body, setBody] = useState('');
  const [visibility, setVisibility] = useState<MessageVisibility | null>(null);

  const canSend = visibility !== null && body.trim().length > 0 && !addMessage.isPending;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSend || visibility === null) {
      return;
    }
    addMessage.mutate(
      { body, visibility },
      {
        onSuccess: () => {
          setBody('');
          setVisibility(null);
        },
      },
    );
  };

  return (
    <Paper variant="outlined" component="form" onSubmit={submit} sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Typography variant="subtitle1" component="p">
          {t('tickets.detail.composer.title')}
        </Typography>

        {addMessage.isError && (
          <Alert severity="error">{t(errorMessageKey(addMessage.error))}</Alert>
        )}

        <ToggleButtonGroup
          exclusive
          value={visibility}
          onChange={(_event, value: MessageVisibility | null) => setVisibility(value)}
          size="small"
          aria-label={t('tickets.detail.composer.visibilityLabel')}
        >
          {MESSAGE_VISIBILITIES.map((option) => (
            <ToggleButton key={option} value={option} sx={{ gap: 1 }}>
              {option === 'public_reply' ? (
                <ForumOutlinedIcon fontSize="small" aria-hidden="true" />
              ) : (
                <LockOutlinedIcon fontSize="small" aria-hidden="true" />
              )}
              {t(`tickets.detail.visibility.${option}`)}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>

        <Typography variant="caption" color="text.secondary">
          {visibility === null
            ? t('tickets.detail.composer.chooseVisibility')
            : visibility === 'internal_note'
              ? t('tickets.detail.visibility.internalNoteHint')
              : t('tickets.detail.composer.publicHint')}
        </Typography>

        <TextField
          id="ticket-message"
          label={t('tickets.detail.composer.body')}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          multiline
          minRows={3}
          fullWidth
        />

        <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
          <Button type="submit" variant="contained" disabled={!canSend}>
            {addMessage.isPending
              ? t('tickets.detail.composer.sending')
              : t('tickets.detail.composer.send')}
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}
