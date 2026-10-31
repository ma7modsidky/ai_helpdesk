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
import { TICKET_PRIORITIES, type TicketPriority } from '@/lib/domain';

import { useCreateTicket } from './queries';
import type { Ticket } from './api';

/** The priority a new ticket starts on when nobody chooses one; the server default too. */
const DEFAULT_PRIORITY: TicketPriority = 'normal';

/**
 * Create a ticket.
 *
 * The requester is contact data, not an account (ADR-020), so an address is required and a
 * name is optional; the server stores the address lowercased and owns the validation. The
 * new ticket is always `open` and unassigned — both are commands after creation, so they are
 * not offered here.
 */
export function CreateTicketDialog({
  workspaceId,
  onCreated,
  onClose,
}: {
  workspaceId: string;
  onCreated: (ticket: Ticket) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const createTicket = useCreateTicket(workspaceId);
  const { fieldErrors, formError, applyError, reset } = useApiFormErrors();

  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [requesterEmail, setRequesterEmail] = useState('');
  const [requesterName, setRequesterName] = useState('');
  const [priority, setPriority] = useState<TicketPriority>(DEFAULT_PRIORITY);
  const [category, setCategory] = useState('');

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reset();
    createTicket.mutate(
      {
        subject: subject.trim(),
        description,
        requester_email: requesterEmail.trim(),
        requester_name: requesterName.trim(),
        priority,
        category: category.trim(),
      },
      { onSuccess: onCreated, onError: applyError },
    );
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <form onSubmit={submit} noValidate>
        <DialogTitle>{t('tickets.create.title')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            <DialogContentText>{t('tickets.create.description')}</DialogContentText>
            {formError && <Alert severity="error">{t(formError)}</Alert>}
            <TextField
              id="ticket-subject"
              label={t('tickets.create.fields.subject')}
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              error={fieldErrors['subject'] !== undefined}
              helperText={fieldErrors['subject']}
              autoFocus
              required
              fullWidth
            />
            <TextField
              id="ticket-description"
              label={t('tickets.create.fields.description')}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              error={fieldErrors['description'] !== undefined}
              helperText={fieldErrors['description']}
              multiline
              minRows={3}
              required
              fullWidth
            />
            <TextField
              id="ticket-requester-email"
              label={t('tickets.create.fields.requesterEmail')}
              type="email"
              value={requesterEmail}
              onChange={(event) => setRequesterEmail(event.target.value)}
              error={fieldErrors['requester_email'] !== undefined}
              helperText={fieldErrors['requester_email']}
              required
              fullWidth
            />
            <TextField
              id="ticket-requester-name"
              label={t('tickets.create.fields.requesterName')}
              value={requesterName}
              onChange={(event) => setRequesterName(event.target.value)}
              error={fieldErrors['requester_name'] !== undefined}
              helperText={fieldErrors['requester_name']}
              fullWidth
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                id="ticket-priority"
                select
                label={t('tickets.inbox.columns.priority')}
                value={priority}
                onChange={(event) => setPriority(event.target.value as TicketPriority)}
                fullWidth
              >
                {TICKET_PRIORITIES.map((value) => (
                  <MenuItem key={value} value={value}>
                    {t(`enums.priority.${value}`)}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                id="ticket-category"
                label={t('tickets.create.fields.category')}
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                error={fieldErrors['category'] !== undefined}
                helperText={fieldErrors['category']}
                fullWidth
              />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose} color="inherit">
            {t('common.actions.cancel')}
          </Button>
          <Button type="submit" variant="contained" disabled={createTicket.isPending}>
            {createTicket.isPending ? t('common.loading') : t('common.actions.create')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
