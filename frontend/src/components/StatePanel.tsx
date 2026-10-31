/**
 * The five states every data screen must handle (07 §2.5).
 *
 * They live in one module so a new screen cannot invent a fourth kind of spinner or a
 * bare "no data", and so the error state cannot forget the request ID that makes a bug
 * report actionable.
 */

import BlockOutlinedIcon from '@mui/icons-material/BlockOutlined';
import InboxOutlinedIcon from '@mui/icons-material/InboxOutlined';
import ReportProblemOutlinedIcon from '@mui/icons-material/ReportProblemOutlined';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { errorMessageKey, isApiError } from '@/lib/api/errors';

interface StatePanelProps {
  readonly icon: ReactNode;
  readonly title: string;
  readonly description?: string | undefined;
  readonly action?: ReactNode | undefined;
  readonly tone?: 'neutral' | 'error';
  readonly role?: 'status' | 'alert';
}

export function StatePanel({
  icon,
  title,
  description,
  action,
  tone = 'neutral',
  role = 'status',
}: StatePanelProps) {
  return (
    <Paper
      variant="outlined"
      role={role}
      sx={{
        p: { xs: 3, sm: 4 },
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        gap: 1,
        borderColor: tone === 'error' ? 'error.main' : 'divider',
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          color: tone === 'error' ? 'error.main' : 'text.secondary',
          display: 'flex',
          mb: 0.5,
        }}
      >
        {icon}
      </Box>
      {/* Not a heading: the page owns the `h1`, and a panel title rendered as one
          would break the document outline instead of describing it. */}
      <Typography variant="subtitle1" component="p">
        {title}
      </Typography>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 480 }}>
          {description}
        </Typography>
      )}
      {action && <Box sx={{ mt: 1.5 }}>{action}</Box>}
    </Paper>
  );
}

/** Inline progress for a panel that is still resolving. */
export function LoadingPanel({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <Stack
      role="status"
      aria-live="polite"
      spacing={1.5}
      sx={{ py: 6, color: 'text.secondary', alignItems: 'center' }}
    >
      <CircularProgress size={28} />
      <Typography variant="body2">{label ?? t('common.loading')}</Typography>
    </Stack>
  );
}

export function EmptyPanel({
  title,
  description,
  action,
}: {
  title: string;
  description?: string | undefined;
  action?: ReactNode | undefined;
}) {
  return (
    <StatePanel
      icon={<InboxOutlinedIcon sx={{ fontSize: 32 }} />}
      title={title}
      description={description}
      action={action}
    />
  );
}

/**
 * The error state names the situation in plain language, offers a retry, and shows the
 * request ID so a support conversation can start from a log line. It never renders the
 * envelope, a stack trace, or a request body.
 */
export function ErrorPanel({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  const requestId = isApiError(error) ? error.requestId : null;

  return (
    <StatePanel
      role="alert"
      tone="error"
      icon={<ReportProblemOutlinedIcon sx={{ fontSize: 32 }} />}
      title={t('errors.title')}
      description={t(errorMessageKey(error))}
      action={
        <Stack spacing={1} sx={{ alignItems: 'center' }}>
          {onRetry && (
            <Button variant="outlined" onClick={onRetry}>
              {t('common.actions.retry')}
            </Button>
          )}
          {requestId && (
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
              {t('errors.requestId', { id: requestId })}
            </Typography>
          )}
        </Stack>
      }
    />
  );
}

/** Shown where the role lacks a capability, instead of an action that would fail. */
export function ForbiddenPanel({ description }: { description?: string | undefined }) {
  const { t } = useTranslation();
  return (
    <StatePanel
      icon={<BlockOutlinedIcon sx={{ fontSize: 32 }} />}
      title={t('errors.forbidden')}
      description={description}
    />
  );
}

/** List placeholder shaped like the rows it stands in for. */
export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  const { t } = useTranslation();
  return (
    <Box role="status" aria-label={t('common.loading')} sx={{ width: '100%' }}>
      <Stack spacing={1}>
        {Array.from({ length: rows }, (_, index) => (
          <Skeleton key={index} variant="rounded" height={64} />
        ))}
      </Stack>
    </Box>
  );
}
