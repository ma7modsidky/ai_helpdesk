import AddIcon from '@mui/icons-material/Add';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
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
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { ErrorPanel, ListSkeleton } from '@/components/StatePanel';
import { useSession } from '@/features/auth/useSession';
import { formatDate } from '@/i18n/formatters';
import { isSupportedLocale, type SupportedLocale } from '@/i18n/locale';
import { isApiError } from '@/lib/api/errors';
import { can } from '@/lib/capabilities';
import { useMyMembership } from '@/lib/workspaceMembers';

import {
  ARTICLE_STATUSES,
  type ArticleStatus,
  type IndexStatus,
  type KnowledgeArticle,
} from './api';
import {
  useArticles,
  useCreateArticle,
  useReindexArticle,
  useSetArticleStatus,
  useUpdateArticle,
} from './queries';

const STATUS_COLOURS: Record<ArticleStatus, 'default' | 'info' | 'success'> = {
  draft: 'info',
  published: 'success',
  archived: 'default',
};

const INDEX_COLOURS: Record<IndexStatus, 'default' | 'info' | 'success' | 'error'> = {
  pending: 'info',
  running: 'info',
  succeeded: 'success',
  failed: 'error',
};

export function ArticleStatusChip({ status }: { readonly status: ArticleStatus }) {
  const { t } = useTranslation();
  return (
    <Chip
      size="small"
      variant="outlined"
      color={STATUS_COLOURS[status]}
      label={t(`knowledge.filters.${status}`)}
    />
  );
}

function IndexChip({ status }: { readonly status: IndexStatus }) {
  const { t } = useTranslation();
  return (
    <Chip
      size="small"
      variant="outlined"
      color={INDEX_COLOURS[status]}
      label={t(`knowledge.index.status.${status}`)}
    />
  );
}

/**
 * Map a refusal to the rule that produced it.
 *
 * The client never renders the server's message (07 §7.2). The knowledge routes have exactly
 * two interesting refusals — a role without `articles.manage`, and an archived article that
 * refuses to be published again — so the status names the rule.
 */
function refusalKey(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 403) {
      return 'knowledge.refusals.capability';
    }
    if (error.status === 409) {
      return 'knowledge.refusals.state';
    }
    if (error.status === 400) {
      return 'errors.validation';
    }
  }
  return 'errors.unexpected';
}

/** Debounce a text field so typing a title query does not send one request per keystroke. */
function useDebouncedValue(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

/**
 * `/app/:workspaceId/knowledge` (T7.6, FR-030, FR-033).
 *
 * Two things this screen refuses to imply: that a draft is usable by the assistant, and that a
 * published article is retrievable while its indexing job is queued or has failed. Both are
 * shown as state, and the warning above the list says the rule once instead of hiding it in a
 * tooltip.
 */
export function KnowledgePage() {
  const { t, i18n } = useTranslation();
  const { workspaceId = '' } = useParams<{ workspaceId: string }>();
  const session = useSession();
  const myMembership = useMyMembership(workspaceId, session.data?.id);

  const locale: SupportedLocale = isSupportedLocale(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : 'en';

  const canManage = can(myMembership.membership?.role, 'articles.manage');

  const [statusFilter, setStatusFilter] = useState<'all' | ArticleStatus>('all');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const debouncedSearch = useDebouncedValue(search, 300);

  const articles = useArticles(workspaceId, {
    status: statusFilter,
    search: debouncedSearch,
    page,
  });

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<KnowledgeArticle | null>(null);

  const openNew = () => {
    setEditing(null);
    setEditorOpen(true);
  };

  const openExisting = (article: KnowledgeArticle) => {
    setEditing(article);
    setEditorOpen(true);
  };

  const rows = articles.data?.results ?? [];
  const total = articles.data?.count ?? 0;
  const filtered = statusFilter !== 'all' || debouncedSearch.trim().length > 0;

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{
          alignItems: { xs: 'flex-start', sm: 'center' },
          justifyContent: 'space-between',
        }}
      >
        <Box>
          <Typography variant="h4" component="h1" gutterBottom>
            {t('knowledge.title')}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {t('knowledge.subtitle')}
          </Typography>
        </Box>
        {canManage ? (
          <Button variant="contained" startIcon={<AddIcon />} onClick={openNew}>
            {t('knowledge.newArticle')}
          </Button>
        ) : null}
      </Stack>

      <Alert severity="info" variant="outlined">
        {t('knowledge.retrievalWarning')}
      </Alert>

      {myMembership.membership !== null && !canManage ? (
        <Typography variant="body2" color="text.secondary">
          {t('knowledge.readOnly', { role: myMembership.membership.role })}
        </Typography>
      ) : null}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <TextField
          select
          label={t('knowledge.filters.status')}
          value={statusFilter}
          onChange={(event) => {
            // A narrower filter is a different result set, so the page counter starts again.
            setStatusFilter(event.target.value as 'all' | ArticleStatus);
            setPage(1);
          }}
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="all">{t('knowledge.filters.all')}</MenuItem>
          {ARTICLE_STATUSES.map((status) => (
            <MenuItem key={status} value={status}>
              {t(`knowledge.filters.${status}`)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          label={t('knowledge.search')}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          fullWidth
          slotProps={{ htmlInput: { maxLength: 100 } }}
        />
      </Stack>

      {articles.isPending ? (
        <ListSkeleton rows={4} />
      ) : articles.isError ? (
        <ErrorPanel error={articles.error} onRetry={() => void articles.refetch()} />
      ) : rows.length === 0 ? (
        <Paper variant="outlined" role="status" sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h6" component="h2" gutterBottom>
            {filtered ? t('knowledge.empty.filtered') : t('knowledge.empty.title')}
          </Typography>
          {filtered ? null : (
            <Typography variant="body2" color="text.secondary">
              {t('knowledge.empty.description')}
            </Typography>
          )}
        </Paper>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>{t('knowledge.columns.title')}</TableCell>
                <TableCell>{t('knowledge.columns.status')}</TableCell>
                <TableCell>{t('knowledge.columns.indexing')}</TableCell>
                <TableCell>{t('knowledge.columns.updated')}</TableCell>
                <TableCell align="right">{t('knowledge.columns.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((article) => (
                <TableRow key={article.id} hover>
                  <TableCell>
                    <Button
                      variant="text"
                      onClick={() => openExisting(article)}
                      sx={{ textTransform: 'none', textAlign: 'start' }}
                    >
                      {article.title}
                    </Button>
                  </TableCell>
                  <TableCell>
                    <ArticleStatusChip status={article.status} />
                  </TableCell>
                  <TableCell>
                    <IndexChip status={article.index_status} />
                  </TableCell>
                  <TableCell>{formatDate(article.updated_at, locale)}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openExisting(article)}>
                      {t('knowledge.open')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {rows.length > 0 ? (
        <Stack
          direction="row"
          spacing={2}
          sx={{ alignItems: 'center', justifyContent: 'flex-end' }}
        >
          <Typography variant="body2" color="text.secondary">
            {t('knowledge.pagination.summary', { total })}
          </Typography>
          <Button
            disabled={!articles.data?.previous || articles.isFetching}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            {t('knowledge.pagination.previous')}
          </Button>
          <Button
            disabled={!articles.data?.next || articles.isFetching}
            onClick={() => setPage((current) => current + 1)}
          >
            {t('knowledge.pagination.next')}
          </Button>
        </Stack>
      ) : null}

      {editorOpen ? (
        <ArticleEditorDialog
          // Remount when another article is opened, so every field starts from that article.
          key={editing?.id ?? 'new'}
          workspaceId={workspaceId}
          article={editing}
          canManage={canManage}
          onClose={() => setEditorOpen(false)}
        />
      ) : null}
    </Stack>
  );
}

interface ArticleEditorProps {
  readonly workspaceId: string;
  readonly article: KnowledgeArticle | null;
  readonly canManage: boolean;
  readonly onClose: () => void;
}

/**
 * The article editor.
 *
 * The lifecycle commands are disabled while the text is unsaved: publishing an unsaved draft
 * would publish the previous text and look like a success, which is the one mistake this
 * screen must not make possible.
 */
function ArticleEditorDialog({ workspaceId, article, canManage, onClose }: ArticleEditorProps) {
  const { t } = useTranslation();

  const [saved, setSaved] = useState<KnowledgeArticle | null>(article);
  const [title, setTitle] = useState(article?.title ?? '');
  const [body, setBody] = useState(article?.body ?? '');
  const [refusal, setRefusal] = useState<string | null>(null);
  const [notice, setNotice] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const create = useCreateArticle(workspaceId);
  const update = useUpdateArticle(workspaceId);
  const setStatus = useSetArticleStatus(workspaceId);
  const reindex = useReindexArticle(workspaceId);

  const dirty = title !== (saved?.title ?? '') || body !== (saved?.body ?? '');

  // A dialog adds no history entry, so the browser's own guard is what covers a reload or a
  // close of the tab. The in-app guard below covers closing the editor.
  useEffect(() => {
    if (!dirty) {
      return undefined;
    }
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [dirty]);

  const close = () => {
    if (dirty) {
      setConfirmDiscard(true);
      return;
    }
    onClose();
  };

  const save = () => {
    setRefusal(null);
    setNotice(false);
    const onSuccess = (next: KnowledgeArticle) => {
      setSaved(next);
      setTitle(next.title);
      setBody(next.body);
      setNotice(true);
    };
    const onError = (error: unknown) => setRefusal(refusalKey(error));

    if (saved === null) {
      create.mutate({ title, body }, { onSuccess, onError });
      return;
    }
    update.mutate({ articleId: saved.id, edit: { title, body } }, { onSuccess, onError });
  };

  const changeStatus = (status: 'published' | 'archived') => {
    if (saved === null) {
      return;
    }
    setRefusal(null);
    setNotice(false);
    setStatus.mutate(
      { articleId: saved.id, status },
      {
        onSuccess: (next) => setSaved(next),
        onError: (error) => setRefusal(refusalKey(error)),
      },
    );
  };

  const requeue = () => {
    if (saved === null) {
      return;
    }
    setRefusal(null);
    setNotice(false);
    reindex.mutate(saved.id, {
      onSuccess: (next) => setSaved(next),
      onError: (error) => setRefusal(refusalKey(error)),
    });
  };

  const busy = create.isPending || update.isPending || setStatus.isPending || reindex.isPending;
  const canPublish = saved !== null && saved.status !== 'published' && saved.status !== 'archived';
  const canArchive = saved !== null && saved.status !== 'archived';
  const saveDisabled =
    !canManage || busy || !dirty || title.trim().length === 0 || body.trim().length === 0;

  return (
    <>
      <Dialog open onClose={close} fullWidth maxWidth="md" aria-labelledby="article-editor-title">
        <DialogTitle id="article-editor-title">
          {saved ? t('knowledge.editor.editTitle') : t('knowledge.editor.createTitle')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Alert severity="info" variant="outlined">
              {t('knowledge.retrievalWarning')}
            </Alert>

            {saved ? (
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <ArticleStatusChip status={saved.status} />
                <IndexChip status={saved.index_status} />
              </Stack>
            ) : null}

            {saved ? <IndexingDetail article={saved} /> : null}

            {refusal ? <Alert severity="error">{t(refusal)}</Alert> : null}
            {notice ? <Alert severity="success">{t('knowledge.editor.saved')}</Alert> : null}

            <TextField
              id="article-title"
              label={t('knowledge.editor.title')}
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
                setNotice(false);
              }}
              disabled={!canManage || busy}
              required
              fullWidth
              slotProps={{ htmlInput: { maxLength: 200 } }}
            />
            <TextField
              id="article-body"
              label={t('knowledge.editor.body')}
              value={body}
              onChange={(event) => {
                setBody(event.target.value);
                setNotice(false);
              }}
              disabled={!canManage || busy}
              required
              fullWidth
              multiline
              minRows={12}
              slotProps={{ htmlInput: { maxLength: 20_000 } }}
            />
            {canManage && dirty ? (
              <Typography variant="body2" color="text.secondary">
                {t('knowledge.editor.dirtyHint')}
              </Typography>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={close}>{t('knowledge.editor.close')}</Button>
          {canManage ? (
            <>
              <Button onClick={requeue} disabled={saved === null || dirty || busy}>
                {t('knowledge.editor.reindex')}
              </Button>
              <Button
                onClick={() => changeStatus('archived')}
                disabled={!canArchive || dirty || busy}
              >
                {t('knowledge.editor.archive')}
              </Button>
              <Button
                onClick={() => changeStatus('published')}
                disabled={!canPublish || dirty || busy}
              >
                {t('knowledge.editor.publish')}
              </Button>
              <Button variant="contained" onClick={save} disabled={saveDisabled}>
                {create.isPending || update.isPending
                  ? t('knowledge.editor.saving')
                  : t('knowledge.editor.save')}
              </Button>
            </>
          ) : null}
        </DialogActions>
      </Dialog>

      <Dialog open={confirmDiscard} onClose={() => setConfirmDiscard(false)}>
        <DialogTitle>{t('knowledge.editor.unsavedTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('knowledge.editor.unsavedDescription')}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDiscard(false)}>
            {t('knowledge.editor.keepEditing')}
          </Button>
          <Button color="error" onClick={onClose}>
            {t('knowledge.editor.discard')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

/** What indexing did, what it stored, and why it may not be retrievable. */
function IndexingDetail({ article }: { readonly article: KnowledgeArticle }) {
  const { t } = useTranslation();

  return (
    <Stack spacing={0.5}>
      <Typography variant="body2" color="text.secondary">
        {t('knowledge.index.chunks', { count: article.chunk_count })}
      </Typography>
      {article.status !== 'published' ? (
        <Typography variant="body2" color="text.secondary">
          {t('knowledge.index.notPublished')}
        </Typography>
      ) : article.indexed_version !== article.version ? (
        <Typography variant="body2" color="text.secondary">
          {t('knowledge.index.stale')}
        </Typography>
      ) : null}
      {article.index_error ? (
        <Alert severity="error" variant="outlined">
          {t('knowledge.index.error', { error: article.index_error })}
        </Alert>
      ) : null}
    </Stack>
  );
}
