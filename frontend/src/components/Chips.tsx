import Chip from '@mui/material/Chip';
import { useTranslation } from 'react-i18next';

import type { InvitationState, MembershipRole } from '@/lib/domain';
import { ROLE_TONES } from '@/theme/tokens';
import { toneSx } from '@/theme/tone';

/**
 * The small labels used wherever a role, a membership, or an invitation is shown.
 *
 * They live together because they are the same kind of thing — a value from a closed
 * vocabulary with a translated label — and because a role chip written twice is how the
 * members table and the invitation screen end up describing the same membership
 * differently (07 §2.4).
 */
export function RoleChip({ role }: { role: MembershipRole }) {
  const { t } = useTranslation();
  return (
    <Chip
      size="small"
      variant="outlined"
      label={t(`enums.role.${role}`)}
      sx={toneSx(ROLE_TONES.light[role], ROLE_TONES.dark[role])}
    />
  );
}

export function MemberStatusChip({ status }: { status: 'active' | 'removed' }) {
  const { t } = useTranslation();
  return (
    <Chip
      size="small"
      variant="outlined"
      color={status === 'active' ? 'success' : 'default'}
      label={t(`enums.memberStatus.${status}`)}
    />
  );
}

/**
 * Invitation state. `expired` is derived by the server from `expires_at` rather than
 * stored, so this chip renders what the API reported instead of recomputing it — a client
 * clock is not the authority on whether a link still works (ADR-026).
 */
const INVITATION_STATE_COLOURS: Record<
  InvitationState,
  'info' | 'warning' | 'success' | 'default'
> = {
  pending: 'info',
  expired: 'warning',
  accepted: 'success',
  revoked: 'default',
};

export function InvitationStateChip({ state }: { state: InvitationState }) {
  const { t } = useTranslation();
  return (
    <Chip
      size="small"
      variant="outlined"
      color={INVITATION_STATE_COLOURS[state]}
      label={t(`enums.invitationState.${state}`)}
    />
  );
}
