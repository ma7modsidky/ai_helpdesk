import AutorenewIcon from '@mui/icons-material/Autorenew';
import CheckCircleOutlinedIcon from '@mui/icons-material/CheckCircleOutlined';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import PriorityHighIcon from '@mui/icons-material/PriorityHigh';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import RemoveIcon from '@mui/icons-material/Remove';
import SouthIcon from '@mui/icons-material/South';
import NorthIcon from '@mui/icons-material/North';
import Chip from '@mui/material/Chip';
import type { SvgIconProps } from '@mui/material/SvgIcon';
import type { ElementType } from 'react';
import { useTranslation } from 'react-i18next';

import type { TicketPriority, TicketStatus } from '@/lib/domain';
import { PRIORITY_TONES, STATUS_TONES } from '@/theme/tokens';
import { toneSx } from '@/theme/tone';

/**
 * Status and priority pills.
 *
 * Each carries a label and an icon as well as a colour, so the meaning survives for a
 * colour-blind reader and in a greyscale screenshot (07 §8). The icons chosen here are
 * along the block axis or non-directional, so none of them mirrors in RTL.
 */
const STATUS_ICONS: Record<TicketStatus, ElementType<Omit<SvgIconProps, 'ref'>>> = {
  open: RadioButtonUncheckedIcon,
  in_progress: AutorenewIcon,
  waiting_on_customer: HourglassEmptyIcon,
  resolved: CheckCircleOutlinedIcon,
  closed: LockOutlinedIcon,
};

const PRIORITY_ICONS: Record<TicketPriority, ElementType<Omit<SvgIconProps, 'ref'>>> = {
  low: SouthIcon,
  normal: RemoveIcon,
  high: NorthIcon,
  urgent: PriorityHighIcon,
};

export function TicketStatusChip({ status }: { status: TicketStatus }) {
  const { t } = useTranslation();
  const Icon = STATUS_ICONS[status];
  return (
    <Chip
      size="small"
      variant="outlined"
      icon={<Icon fontSize="small" />}
      label={t(`enums.status.${status}`)}
      sx={toneSx(STATUS_TONES.light[status], STATUS_TONES.dark[status])}
    />
  );
}

export function TicketPriorityChip({ priority }: { priority: TicketPriority }) {
  const { t } = useTranslation();
  const Icon = PRIORITY_ICONS[priority];
  return (
    <Chip
      size="small"
      variant="outlined"
      icon={<Icon fontSize="small" />}
      label={t(`enums.priority.${priority}`)}
      sx={toneSx(PRIORITY_TONES.light[priority], PRIORITY_TONES.dark[priority])}
    />
  );
}
