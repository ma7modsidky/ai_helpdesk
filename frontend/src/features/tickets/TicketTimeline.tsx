import ForumOutlinedIcon from '@mui/icons-material/ForumOutlined';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';

import { EmptyPanel, ListSkeleton } from '@/components/StatePanel';
import { formatDateTime } from '@/i18n/formatters';
import { isSupportedLocale, type SupportedLocale } from '@/i18n/locale';
import type { TicketMessage } from './api';

/**
 * The conversation (07 §6.6).
 *
 * The one thing this must never do is blur a public reply and an internal note (FR-014):
 * the two differ by label, icon, colour, and indentation test, so a reader cannot mistake a
 * note for something a customer has seen — and the same distinction survives a greyscale
 * screenshot, because the label and icon carry it.
 */
function MessageCard({ message, locale }: { message: TicketMessage; locale: SupportedLocale }) {
  const { t } = useTranslation();
  const isNote = message.visibility === 'internal_note';
  const author = message.author?.email ?? t('tickets.detail.timeline.systemAuthor');

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        borderInlineStartWidth: 4,
        borderInlineStartStyle: 'solid',
        borderInlineStartColor: isNote ? 'warning.main' : 'divider',
        bgcolor: isNote ? 'action.hover' : 'background.paper',
      }}
    >
      <Stack spacing={1}>
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}
        >
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Chip
              size="small"
              variant="outlined"
              color={isNote ? 'warning' : 'default'}
              icon={
                isNote ? (
                  <LockOutlinedIcon fontSize="small" />
                ) : (
                  <ForumOutlinedIcon fontSize="small" />
                )
              }
              label={t(`tickets.detail.visibility.${message.visibility}`)}
            />
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {author}
            </Typography>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            {formatDateTime(message.created_at, locale)}
          </Typography>
        </Stack>

        {isNote && (
          <Typography variant="caption" color="text.secondary">
            {t('tickets.detail.visibility.internalNoteHint')}
          </Typography>
        )}

        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
          {message.body}
        </Typography>
      </Stack>
    </Paper>
  );
}

export function TicketTimeline({
  messages,
  isPending,
  truncated,
}: {
  messages: readonly TicketMessage[];
  isPending: boolean;
  truncated: boolean;
}) {
  const { t, i18n } = useTranslation();
  const locale: SupportedLocale = isSupportedLocale(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : 'en';

  if (isPending) {
    return <ListSkeleton rows={2} />;
  }

  if (messages.length === 0) {
    return (
      <EmptyPanel
        title={t('tickets.detail.timeline.empty.title')}
        description={t('tickets.detail.timeline.empty.description')}
      />
    );
  }

  return (
    <Stack spacing={1.5} component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }}>
      {truncated && (
        <Box component="li">
          <Typography variant="caption" color="text.secondary">
            {t('tickets.detail.timeline.truncated')}
          </Typography>
        </Box>
      )}
      {messages.map((message) => (
        <Box component="li" key={message.id}>
          <MessageCard message={message} locale={locale} />
        </Box>
      ))}
    </Stack>
  );
}
