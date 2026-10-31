import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useParams } from 'react-router-dom';

import { ErrorPanel, LoadingPanel } from '@/components/StatePanel';
import { formatDateTime } from '@/i18n/formatters';
import { isSupportedLocale, type SupportedLocale } from '@/i18n/locale';
import { isApiError } from '@/lib/api/errors';
import { can } from '@/lib/capabilities';
import { TICKET_PRIORITIES, TICKET_STATUSES, type TicketStatus } from '@/lib/domain';
import { useMyMembership, useWorkspaceMembers } from '@/lib/workspaceMembers';

import { useSession } from '@/features/auth/useSession';

import { DEFAULT_WORKSPACE_SEGMENT, workspacePath } from '@/app/navigation';

import { TicketPriorityChip, TicketStatusChip } from './TicketChips';
import { TicketComposer } from './TicketComposer';
import { TicketTimeline } from './TicketTimeline';
import {
  MESSAGES_PAGE_SIZE,
  useTicket,
  useTicketMessages,
  useTransitionTicket,
  useAssignTicket,
  useUpdateTicketFields,
} from './queries';
import type { TicketPriority } from '@/lib/domain';

/**
 * `/app/:workspaceId/tickets/:ticketId` (T4.10).
 *
 * The screen is a read of one ticket plus the three ways to change it, each going through
 * the command the server owns: a field edit under `If-Match` (ADR-022), an assignment, and
 * a transition. Commands are not optimistic — the server decides legality, and the response
 * it returns is what the screen shows, so an illegal transition is refused rather than
 * predicted. Controls the caller's role cannot use are disabled with an explanation.
 */
export function TicketDetailPage() {
  const { t, i18n } = useTranslation();
  const { workspaceId = '', ticketId = '' } = useParams<{
    workspaceId: string;
    ticketId: string;
  }>();
  const session = useSession();
  const myMembership = useMyMembership(workspaceId, session.data?.id);
  const role = myMembership.membership?.role ?? null;
  const members = useWorkspaceMembers(workspaceId);

  const ticket = useTicket(workspaceId, ticketId);
  const messages = useTicketMessages(workspaceId, ticketId);
  const updateFields = useUpdateTicketFields(workspaceId, ticketId);
  const assign = useAssignTicket(workspaceId, ticketId);
  const transition = useTransitionTicket(workspaceId, ticketId);

  const [conflict, setConflict] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);

  const locale: SupportedLocale = isSupportedLocale(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : 'en';
  const inboxPath = workspacePath(workspaceId, DEFAULT_WORKSPACE_SEGMENT);

  if (ticket.isPending) {
    return <LoadingPanel />;
  }

  if (ticket.isError) {
    return (
      <Stack spacing={2}>
        <ErrorPanel error={ticket.error} onRetry={() => void ticket.refetch()} />
        <Box>
          <Button component={RouterLink} to={inboxPath} variant="outlined">
            {t('tickets.detail.backToInbox')}
          </Button>
        </Box>
      </Stack>
    );
  }

  const data = ticket.data;
  const canEdit = can(role, 'tickets.edit');
  const canTransition = can(role, 'tickets.transition');
  const canAssignSelf = can(role, 'tickets.assign_self');
  const canAssignOthers = can(role, 'tickets.assign_others');
  const canAssign = canAssignSelf || canAssignOthers;

  const activeMembers = (members.data ?? []).filter((entry) => entry.status === 'active');
  const assigneeOptions = activeMembers.filter(
    (entry) => canAssignOthers || entry.user_id === session.data?.id,
  );
  const assigneeLabel =
    activeMembers.find((entry) => entry.user_id === data.assignee_id)?.email ??
    t('tickets.inbox.filters.unassigned');

  const editField = (edit: { priority?: TicketPriority }) => {
    setRefusal(null);
    setConflict(false);
    updateFields.mutate(
      { edit, version: data.version },
      {
        onError: (error) => {
          // A `409` here is the version check: this screen is holding a stale read.
          if (isApiError(error) && error.status === 409) {
            setConflict(true);
            return;
          }
          setRefusal(
            isApiError(error) && error.status === 403 ? 'errors.forbidden' : 'errors.unexpected',
          );
        },
      },
    );
  };

  const applyTransition = (status: TicketStatus) => {
    setRefusal(null);
    transition.mutate(status, {
      onError: (error) => {
        if (isApiError(error) && error.status === 409) {
          setRefusal('tickets.detail.refusals.transition');
          return;
        }
        setRefusal(
          isApiError(error) && error.status === 403 ? 'errors.forbidden' : 'errors.unexpected',
        );
      },
    });
  };

  const applyAssignment = (assigneeId: string | null) => {
    setRefusal(null);
    assign.mutate(assigneeId, {
      onError: (error) => {
        if (isApiError(error) && error.status === 400) {
          setRefusal('tickets.detail.refusals.assignee');
          return;
        }
        setRefusal(
          isApiError(error) && error.status === 403 ? 'errors.forbidden' : 'errors.unexpected',
        );
      },
    });
  };

  return (
    <Stack spacing={2.5}>
      <Stack spacing={0.5}>
        <Link component={RouterLink} to={inboxPath} variant="caption">
          {t('tickets.detail.backToInbox')}
        </Link>
        <Typography component="h1" variant="h5">
          {data.subject}
        </Typography>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
          <TicketStatusChip status={data.status} />
          <TicketPriorityChip priority={data.priority} />
          <Typography variant="caption" color="text.secondary">
            {t('tickets.detail.requester', {
              requester: data.requester_name || data.requester_email,
            })}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('tickets.detail.created', { date: formatDateTime(data.created_at, locale) })}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('tickets.detail.updated', { date: formatDateTime(data.updated_at, locale) })}
          </Typography>
        </Stack>
      </Stack>

      {conflict && (
        <Alert
          severity="warning"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => {
                void ticket.refetch();
                setConflict(false);
              }}
            >
              {t('common.actions.reload')}
            </Button>
          }
        >
          {t('tickets.detail.conflict')}
        </Alert>
      )}

      {refusal && <Alert severity="warning">{t(refusal)}</Alert>}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Typography variant="subtitle1" component="p">
            {t('tickets.detail.controls.title')}
          </Typography>

          <Box
            sx={{
              display: 'grid',
              gap: 2,
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
            }}
          >
            <TextField
              id="ticket-status"
              select
              label={t('tickets.inbox.columns.status')}
              value={data.status}
              onChange={(event) => applyTransition(event.target.value as TicketStatus)}
              disabled={!canTransition}
              fullWidth
            >
              {TICKET_STATUSES.map((status) => (
                <MenuItem key={status} value={status}>
                  {t(`enums.status.${status}`)}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              id="ticket-priority"
              select
              label={t('tickets.inbox.columns.priority')}
              value={data.priority}
              onChange={(event) => editField({ priority: event.target.value as TicketPriority })}
              disabled={!canEdit}
              fullWidth
            >
              {TICKET_PRIORITIES.map((priority) => (
                <MenuItem key={priority} value={priority}>
                  {t(`enums.priority.${priority}`)}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              id="ticket-assignee"
              select
              label={t('tickets.inbox.filters.assignee')}
              value={data.assignee_id ?? ''}
              onChange={(event) =>
                applyAssignment(event.target.value === '' ? null : event.target.value)
              }
              disabled={!canAssign}
              helperText={canAssign ? assigneeLabel : undefined}
              fullWidth
            >
              <MenuItem value="">{t('tickets.inbox.filters.unassigned')}</MenuItem>
              {assigneeOptions.map((member) => (
                <MenuItem key={member.user_id} value={member.user_id}>
                  {member.email}
                </MenuItem>
              ))}
            </TextField>
          </Box>

          {!canEdit && !canTransition && !canAssign && (
            <Typography variant="caption" color="text.secondary">
              {t('tickets.detail.controls.readOnly', {
                role: role === null ? t('enums.role.agent') : t(`enums.role.${role}`),
              })}
            </Typography>
          )}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1}>
          <Typography variant="subtitle1" component="p">
            {t('tickets.detail.description')}
          </Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {data.description}
          </Typography>
        </Stack>
      </Paper>

      <Stack spacing={1.5}>
        <Typography variant="subtitle1" component="p">
          {t('tickets.detail.timeline.title')}
        </Typography>
        <TicketTimeline
          messages={messages.data?.results ?? []}
          isPending={messages.isPending}
          truncated={(messages.data?.count ?? 0) > MESSAGES_PAGE_SIZE}
        />
      </Stack>

      <TicketComposer workspaceId={workspaceId} ticketId={ticketId} />
    </Stack>
  );
}
