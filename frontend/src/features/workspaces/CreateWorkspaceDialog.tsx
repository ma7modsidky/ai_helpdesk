import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { useApiFormErrors } from '@/components/useApiFormSubmit';

import { useCreateWorkspace } from './queries';
import type { Workspace } from './api';

/**
 * Derive a URL-safe slug from the name, as a convenience only.
 *
 * The server validates the slug and rejects a duplicate with a field error, which is the
 * one behaviour this must not try to predict: only the database knows whether a slug is
 * free, and a client-side check would either be a race or a leak.
 */
export function slugify(value: string): string {
  return value
    .normalize('NFKD')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 50);
}

function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/**
 * Mounted only while open, so the fields always start empty: a reset effect would be a
 * second source of state, and the caller decides when the dialog exists.
 */
export function CreateWorkspaceDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (workspace: Workspace) => void;
}) {
  const { t } = useTranslation();
  const createMutation = useCreateWorkspace();
  const { fieldErrors, formError, applyError, reset } = useApiFormErrors();

  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [timezone, setTimezone] = useState(browserTimezone);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reset();
    createMutation.mutate(
      { name: name.trim(), slug: slug.trim(), timezone },
      {
        onSuccess: (workspace) => {
          onCreated(workspace);
          onClose();
        },
        onError: applyError,
      },
    );
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <form onSubmit={submit} noValidate>
        <DialogTitle>{t('workspaces.createTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t('workspaces.createDescription')}</DialogContentText>
          <Stack spacing={2}>
            {formError && <Alert severity="error">{t(formError)}</Alert>}
            <TextField
              id="workspace-name"
              label={t('workspaces.fields.name')}
              value={name}
              onChange={(event) => {
                const next = event.target.value;
                setName(next);
                if (!slugTouched) {
                  setSlug(slugify(next));
                }
              }}
              error={fieldErrors['name'] !== undefined}
              helperText={fieldErrors['name']}
              autoFocus
              required
              fullWidth
            />
            <TextField
              id="workspace-slug"
              label={t('workspaces.fields.slug')}
              value={slug}
              onChange={(event) => {
                setSlugTouched(true);
                setSlug(event.target.value);
              }}
              error={fieldErrors['slug'] !== undefined}
              helperText={fieldErrors['slug'] ?? t('workspaces.fields.slugHint')}
              required
              fullWidth
            />
            <TextField
              id="workspace-timezone"
              label={t('workspaces.fields.timezone')}
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              error={fieldErrors['timezone'] !== undefined}
              helperText={fieldErrors['timezone']}
              required
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose} color="inherit">
            {t('common.actions.cancel')}
          </Button>
          <Button type="submit" variant="contained" disabled={createMutation.isPending}>
            {t('common.actions.create')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
