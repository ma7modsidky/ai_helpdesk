import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorPanel, LoadingPanel } from '@/components/StatePanel';
import { errorMessageKey } from '@/lib/api/errors';

import type { ReplyDraft } from './api';
import { useAddMessage, useRequestDraft, useTicketAIStatus } from './queries';

/**
 * The AI reply draft (T6.3, 07 §6.6, ADR-002).
 *
 * Three things this panel must never blur:
 *
 * 1. **A draft is not a reply.** It is editable text that reaches no one until the agent
 *    presses send, and that send is the existing message endpoint — there is no second,
 *    quieter way to publish.
 * 2. **A citation is shown, not asserted.** Every source the server kept is rendered with its
 *    title; a draft with no sources says so in a warning, because "not grounded in any
 *    knowledge article" is information the reader needs before sending (FR-035).
 * 3. **A job has a state.** Queued, running, failed, and ready are distinguished, and the poll
 *    stops at a terminal one, so a stuck worker becomes a visible failure rather than a spinner
 *    that never ends.
 */
export function TicketAIPanel({
  workspaceId,
  ticketId,
  canComment,
}: {
  workspaceId: string;
  ticketId: string;
  canComment: boolean;
}) {
  const { t } = useTranslation();
  const aiStatus = useTicketAIStatus(workspaceId, ticketId);
  const requestDraft = useRequestDraft(workspaceId, ticketId);

  const draft = aiStatus.data?.draft ?? null;
  const inFlight = draft?.status === 'pending' || draft?.status === 'running';
  const busy = requestDraft.isPending || inFlight;

  const generate = () => {
    requestDraft.mutate();
  };

  return (
    <Paper
      variant="outlined"
      component="section"
      aria-label={t('tickets.detail.ai.title')}
      sx={{ p: 2 }}
    >
      <Stack spacing={2}>
        <Stack spacing={0.5}>
          <Typography variant="subtitle1" component="p">
            {t('tickets.detail.ai.title')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('tickets.detail.ai.intro')}
          </Typography>
        </Stack>

        {aiStatus.isPending && <LoadingPanel label={t('tickets.detail.ai.loading')} />}

        {aiStatus.isError && (
          <ErrorPanel error={aiStatus.error} onRetry={() => void aiStatus.refetch()} />
        )}

        {aiStatus.isSuccess && (
          <Stack spacing={2}>
            {requestDraft.isError && (
              <Alert severity="error">{t(errorMessageKey(requestDraft.error))}</Alert>
            )}

            {draft === null && (
              <Box>
                <Button variant="contained" onClick={generate} disabled={!canComment || busy}>
                  {busy ? t('tickets.detail.ai.generating') : t('tickets.detail.ai.generate')}
                </Button>
                {!canComment && (
                  <Typography variant="caption" color="text.secondary" component="p">
                    {t('tickets.detail.ai.readOnly')}
                  </Typography>
                )}
              </Box>
            )}

            {draft !== null && inFlight && (
              <Stack spacing={1.5} role="status" aria-live="polite">
                <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
                  <CircularProgress size={20} aria-label={t('tickets.detail.ai.pending')} />
                  <Typography variant="body2" color="text.secondary">
                    {t('tickets.detail.ai.pending')}
                  </Typography>
                </Stack>
                <Box>
                  <Button variant="outlined" size="small" onClick={() => void aiStatus.refetch()}>
                    {t('tickets.detail.ai.refresh')}
                  </Button>
                </Box>
              </Stack>
            )}

            {draft !== null && draft.status === 'failed' && (
              <Stack spacing={1.5}>
                <Alert severity="error">{t('tickets.detail.ai.failed')}</Alert>
                <Box>
                  <Button variant="outlined" onClick={generate} disabled={!canComment || busy}>
                    {t('tickets.detail.ai.failedRetry')}
                  </Button>
                </Box>
              </Stack>
            )}

            {draft !== null && draft.status === 'succeeded' && (
              // Keyed by job id: a regenerated draft mounts a fresh editor with the new text,
              // instead of an effect copying it over writing the agent may already have done.
              <DraftReview
                key={draft.id}
                workspaceId={workspaceId}
                ticketId={ticketId}
                draft={draft}
                canComment={canComment}
                busy={busy}
                onGenerate={generate}
              />
            )}
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}

function DraftReview({
  workspaceId,
  ticketId,
  draft,
  canComment,
  busy,
  onGenerate,
}: {
  workspaceId: string;
  ticketId: string;
  draft: ReplyDraft;
  canComment: boolean;
  busy: boolean;
  onGenerate: () => void;
}) {
  const { t } = useTranslation();
  const addMessage = useAddMessage(workspaceId, ticketId);

  const [text, setText] = useState(draft.draft_text);
  const [sent, setSent] = useState(false);

  const canSend = canComment && text.trim().length > 0 && !addMessage.isPending && !busy;

  const send = () => {
    const body = text.trim();
    if (body.length === 0) {
      return;
    }
    addMessage.mutate(
      { body, visibility: 'public_reply' },
      {
        onSuccess: () => {
          setText('');
          setSent(true);
        },
      },
    );
  };

  return (
    <Stack spacing={2}>
      <Alert severity="info">{t('tickets.detail.ai.reviewRequired')}</Alert>

      {addMessage.isError && <Alert severity="error">{t(errorMessageKey(addMessage.error))}</Alert>}
      {sent && <Alert severity="success">{t('tickets.detail.ai.sent')}</Alert>}

      {draft.source_articles.length > 0 ? (
        <Stack spacing={1}>
          <Typography variant="caption" color="text.secondary">
            {t('tickets.detail.ai.sourcesTotal', { total: draft.source_articles.length })}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
            {draft.source_articles.map((source) => (
              <Chip key={source.article_id} size="small" variant="outlined" label={source.title} />
            ))}
          </Stack>
        </Stack>
      ) : (
        <Alert severity="warning">{t('tickets.detail.ai.noSources')}</Alert>
      )}

      <TextField
        id="ticket-ai-draft"
        label={t('tickets.detail.ai.editorLabel')}
        value={text}
        onChange={(event) => setText(event.target.value)}
        multiline
        minRows={4}
        fullWidth
        helperText={text.trim().length === 0 ? t('tickets.detail.ai.emptyEditor') : undefined}
      />

      <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
        <Button variant="outlined" onClick={onGenerate} disabled={!canComment || busy}>
          {t('tickets.detail.ai.regenerate')}
        </Button>
        <Button variant="contained" onClick={send} disabled={!canSend}>
          {addMessage.isPending ? t('tickets.detail.ai.sending') : t('tickets.detail.ai.send')}
        </Button>
      </Stack>
    </Stack>
  );
}
