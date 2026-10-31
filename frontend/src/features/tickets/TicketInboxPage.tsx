import AddIcon from '@mui/icons-material/Add';
import SearchIcon from '@mui/icons-material/Search';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import Pagination from '@mui/material/Pagination';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { EmptyPanel, ErrorPanel, ListSkeleton } from '@/components/StatePanel';
import { formatRelativeTime } from '@/i18n/formatters';
import { isSupportedLocale, type SupportedLocale } from '@/i18n/locale';
import { queryKeys } from '@/lib/api/queryKeys';
import {
  DEFAULT_TICKET_ORDERING,
  TICKET_PRIORITIES,
  TICKET_STATUSES,
  type TicketPriority,
  type TicketStatus,
} from '@/lib/domain';
import { useDebouncedValue } from '@/lib/useDebouncedValue';

import { CreateTicketDialog } from './CreateTicketDialog';
import { TicketPriorityChip, TicketStatusChip } from './TicketChips';
import { listTickets, type TicketListQuery } from './api';
import { ticketPath } from './paths';

/** Matches the contract's default page size, so a URL from the API is reproducible here. */
const PAGE_SIZE = 25;

const ASSIGNEE_FILTERS = ['', 'me', 'unassigned'] as const;

/** The four orderings the inbox offers, each already on the server's allowlist. */
const ORDERINGS = [
  { value: '-updated_at', key: 'recent' },
  { value: '-created_at', key: 'newest' },
  { value: '-priority', key: 'priority' },
  { value: 'status', key: 'status' },
] as const;

function parseStatus(value: string | null): TicketStatus | undefined {
  return TICKET_STATUSES.find((status) => status === value);
}

function parsePriority(value: string | null): TicketPriority | undefined {
  return TICKET_PRIORITIES.find((priority) => priority === value);
}

function parseAssignee(value: string | null): string {
  return ASSIGNEE_FILTERS.find((candidate) => candidate === value) ?? '';
}

function parseOrdering(value: string | null): string {
  return ORDERINGS.find((option) => option.value === value)?.value ?? DEFAULT_TICKET_ORDERING;
}

function parsePage(value: string | null): number {
  const parsed = Number.parseInt(value ?? '1', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

/**
 * The inbox: the queue for one workspace.
 *
 * Every filter lives in the URL, so a view is shareable, reload-safe, and correct with the
 * back button, and the request is always built from the URL rather than from component
 * state that could drift from what the user sees (07 §5). Nothing is filtered on the
 * client: the server owns the query, the ordering allowlist, and the page size (ADR-023).
 */
export function TicketInboxPage() {
  const { t, i18n } = useTranslation();
  const { workspaceId = '' } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);

  const locale: SupportedLocale = isSupportedLocale(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : 'en';

  const status = parseStatus(searchParams.get('status'));
  const priority = parsePriority(searchParams.get('priority'));
  const assignee = parseAssignee(searchParams.get('assignee'));
  const search = searchParams.get('search') ?? '';
  const ordering = parseOrdering(searchParams.get('ordering'));
  const page = parsePage(searchParams.get('page'));

  const [searchInput, setSearchInput] = useState(search);
  const debouncedSearch = useDebouncedValue(searchInput, 300);

  const applyParams = (changes: Record<string, string | number | undefined>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(changes)) {
      if (value === undefined || value === '') {
        next.delete(key);
      } else {
        next.set(key, String(value));
      }
    }
    setSearchParams(next, { replace: true });
  };

  // A debounced query must not race the URL: the value is pushed into the URL once it
  // settles, and the request reads the URL, so there is a single source of truth.
  useEffect(() => {
    if (debouncedSearch !== search) {
      applyParams({ search: debouncedSearch, page: 1 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const query: TicketListQuery = {
    status,
    priority,
    assignee: assignee === '' ? undefined : assignee,
    search,
    ordering,
    page,
  };

  const tickets = useQuery({
    queryKey: queryKeys.tickets(workspaceId, query),
    queryFn: ({ signal }) => listTickets(workspaceId, query, PAGE_SIZE, signal),
    enabled: workspaceId.length > 0,
    placeholderData: (previous) => previous,
  });

  const hasFilters =
    status !== undefined || priority !== undefined || assignee !== '' || search.trim() !== '';
  const totalPages = tickets.data ? Math.max(1, Math.ceil(tickets.data.count / PAGE_SIZE)) : 1;

  return (
    <Stack spacing={2.5}>
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap' }}
      >
        <Stack spacing={0.5}>
          <Typography component="h1" variant="h5">
            {t('tickets.inbox.title')}
          </Typography>
          {tickets.data && (
            <Typography variant="body2" color="text.secondary">
              {t('tickets.inbox.count', { count: tickets.data.count })}
            </Typography>
          )}
        </Stack>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
          {t('tickets.create.action')}
        </Button>
      </Stack>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Box
          sx={{
            display: 'grid',
            gap: 2,
            gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '2fr 1fr 1fr 1fr 1fr' },
          }}
        >
          <TextField
            id="inbox-search"
            label={t('tickets.inbox.filters.search')}
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder={t('tickets.inbox.filters.searchPlaceholder')}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" aria-hidden="true" />
                  </InputAdornment>
                ),
              },
            }}
          />
          <TextField
            id="inbox-status"
            select
            label={t('tickets.inbox.filters.status')}
            value={status ?? ''}
            onChange={(event) => applyParams({ status: event.target.value, page: 1 })}
          >
            <MenuItem value="">{t('tickets.inbox.filters.anyStatus')}</MenuItem>
            {TICKET_STATUSES.map((value) => (
              <MenuItem key={value} value={value}>
                {t(`enums.status.${value}`)}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            id="inbox-priority"
            select
            label={t('tickets.inbox.filters.priority')}
            value={priority ?? ''}
            onChange={(event) => applyParams({ priority: event.target.value, page: 1 })}
          >
            <MenuItem value="">{t('tickets.inbox.filters.anyPriority')}</MenuItem>
            {TICKET_PRIORITIES.map((value) => (
              <MenuItem key={value} value={value}>
                {t(`enums.priority.${value}`)}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            id="inbox-assignee"
            select
            label={t('tickets.inbox.filters.assignee')}
            value={assignee}
            onChange={(event) => applyParams({ assignee: event.target.value, page: 1 })}
          >
            <MenuItem value="">{t('tickets.inbox.filters.anyAssignee')}</MenuItem>
            <MenuItem value="me">{t('tickets.inbox.filters.me')}</MenuItem>
            <MenuItem value="unassigned">{t('tickets.inbox.filters.unassigned')}</MenuItem>
          </TextField>
          <TextField
            id="inbox-ordering"
            select
            label={t('tickets.inbox.filters.ordering')}
            value={ordering}
            onChange={(event) => applyParams({ ordering: event.target.value, page: 1 })}
          >
            {ORDERINGS.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {t(`tickets.inbox.ordering.${option.key}`)}
              </MenuItem>
            ))}
          </TextField>
        </Box>
      </Paper>

      {tickets.isPending && <ListSkeleton rows={5} />}

      {tickets.isError && (
        <ErrorPanel error={tickets.error} onRetry={() => void tickets.refetch()} />
      )}

      {tickets.data && tickets.data.results.length === 0 && !hasFilters && (
        <EmptyPanel
          title={t('tickets.inbox.empty.title')}
          description={t('tickets.inbox.empty.description')}
        />
      )}

      {tickets.data && tickets.data.results.length === 0 && hasFilters && (
        <EmptyPanel
          title={t('tickets.inbox.filteredEmpty.title')}
          description={t('tickets.inbox.filteredEmpty.description')}
          action={
            <Button
              variant="outlined"
              onClick={() => {
                setSearchInput('');
                setSearchParams(new URLSearchParams(), { replace: true });
              }}
            >
              {t('tickets.inbox.filteredEmpty.action')}
            </Button>
          }
        />
      )}

      {tickets.data && tickets.data.results.length > 0 && (
        <>
          <TableContainer component={Paper} variant="outlined">
            <Table size="small" aria-label={t('tickets.inbox.title')}>
              <TableHead>
                <TableRow>
                  <TableCell>{t('tickets.inbox.columns.subject')}</TableCell>
                  <TableCell>{t('tickets.inbox.columns.status')}</TableCell>
                  <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                    {t('tickets.inbox.columns.priority')}
                  </TableCell>
                  <TableCell sx={{ display: { xs: 'none', lg: 'table-cell' } }}>
                    {t('tickets.inbox.columns.requester')}
                  </TableCell>
                  <TableCell sx={{ textAlign: 'end' }}>
                    {t('tickets.inbox.columns.updated')}
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tickets.data.results.map((ticket) => (
                  <TableRow key={ticket.id} hover>
                    <TableCell sx={{ maxWidth: 360 }}>
                      <Link
                        component={RouterLink}
                        to={ticketPath(workspaceId, ticket.id)}
                        variant="body2"
                        noWrap
                        title={ticket.subject}
                        sx={{ display: 'block' }}
                      >
                        {ticket.subject}
                      </Link>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {ticket.requester_email}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <TicketStatusChip status={ticket.status} />
                    </TableCell>
                    <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                      <TicketPriorityChip priority={ticket.priority} />
                    </TableCell>
                    <TableCell
                      sx={{ display: { xs: 'none', lg: 'table-cell' }, color: 'text.secondary' }}
                    >
                      {ticket.requester_name || ticket.requester_email}
                    </TableCell>
                    <TableCell
                      sx={{ textAlign: 'end', whiteSpace: 'nowrap', color: 'text.secondary' }}
                    >
                      {formatRelativeTime(ticket.updated_at, locale)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {totalPages > 1 && (
            <Stack sx={{ alignItems: 'center' }}>
              <Pagination
                count={totalPages}
                page={page}
                onChange={(_event, value) => applyParams({ page: value })}
                showFirstButton
                showLastButton
                siblingCount={1}
              />
            </Stack>
          )}
        </>
      )}

      {createOpen && (
        <CreateTicketDialog
          workspaceId={workspaceId}
          onClose={() => setCreateOpen(false)}
          onCreated={(ticket) => {
            setCreateOpen(false);
            void navigate(ticketPath(workspaceId, ticket.id));
          }}
        />
      )}
    </Stack>
  );
}
