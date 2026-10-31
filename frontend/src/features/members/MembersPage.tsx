import AddIcon from '@mui/icons-material/Add';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
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
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { InvitationStateChip, MemberStatusChip, RoleChip } from '@/components/Chips';
import { ErrorPanel, ListSkeleton } from '@/components/StatePanel';
import { formatDate, formatRelativeTime } from '@/i18n/formatters';
import { isSupportedLocale, type SupportedLocale } from '@/i18n/locale';
import { isApiError } from '@/lib/api/errors';
import { can, canManageRole, grantableRoles } from '@/lib/capabilities';
import type { MembershipRole } from '@/lib/domain';
import { useMyMembership } from '@/lib/workspaceMembers';

import { useSession } from '@/features/auth/useSession';

import { AcceptLinkDialog } from './AcceptLinkDialog';
import { InviteMemberDialog } from './InviteMemberDialog';
import { TransferOwnershipDialog } from './TransferOwnershipDialog';
import type { Invitation, InvitationFilter, Member, MemberChange } from './api';
import {
  useChangeMember,
  useInvitations,
  useMembers,
  useResendInvitation,
  useRevokeInvitation,
} from './queries';

const INVITATION_FILTERS: readonly InvitationFilter[] = ['pending', 'accepted', 'revoked', 'all'];

/**
 * Translate a refusal into the explanation for the rule that produced it.
 *
 * The client never renders the server's message directly (07 §7.2), and each endpoint has
 * one state-conflict case, so the code plus the operation names the rule exactly.
 */
function memberRefusalKey(error: unknown): string {
  if (isApiError(error) && error.status === 409) {
    return 'members.refusals.lastOwner';
  }
  if (isApiError(error) && error.status === 403) {
    return 'members.refusals.capability';
  }
  return 'errors.unexpected';
}

function invitationRefusalKey(error: unknown, operation: 'create' | 'resend' | 'revoke'): string {
  if (isApiError(error) && error.status === 409) {
    return operation === 'create'
      ? 'members.refusals.duplicateInvitation'
      : 'members.refusals.notPending';
  }
  if (isApiError(error) && error.status === 403) {
    return 'members.refusals.capability';
  }
  return 'errors.unexpected';
}

/**
 * `/app/:workspaceId/settings/members` (T4.8).
 *
 * The screen mirrors the server's rules rather than guessing them: a control the caller's
 * role cannot use is not rendered, the role options come from the same hierarchy the
 * server enforces, and every refusal is displayed in place instead of being swallowed. The
 * invitation link is shown exactly once, at creation, because the API returns it once.
 */
export function MembersPage() {
  const { t, i18n } = useTranslation();
  const { workspaceId = '' } = useParams<{ workspaceId: string }>();
  const session = useSession();
  const myMembership = useMyMembership(workspaceId, session.data?.id);

  const locale: SupportedLocale = isSupportedLocale(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : 'en';

  const role = myMembership.membership?.role ?? null;
  const canManage = can(role, 'members.manage');

  const members = useMembers(workspaceId);
  const changeMember = useChangeMember(workspaceId);
  const resendInvitation = useResendInvitation(workspaceId);
  const revokeInvitation = useRevokeInvitation(workspaceId);

  const [invitationFilter, setInvitationFilter] = useState<InvitationFilter>('pending');
  const invitations = useInvitations(workspaceId, invitationFilter);

  const [memberRefusal, setMemberRefusal] = useState<{ id: string; key: string } | null>(null);
  const [invitationRefusal, setInvitationRefusal] = useState<{ email: string; key: string } | null>(
    null,
  );
  const [inviteOpen, setInviteOpen] = useState(false);
  const [transferTarget, setTransferTarget] = useState<Member | null>(null);
  const [acceptLink, setAcceptLink] = useState<{ path: string; role: MembershipRole } | null>(null);

  const rows = members.data?.results ?? [];
  const callerId = session.data?.id ?? null;

  const applyMemberChange = (member: Member, body: MemberChange) => {
    setMemberRefusal(null);
    changeMember.mutate(
      { membershipId: member.id, change: body },
      { onError: (error) => setMemberRefusal({ id: member.id, key: memberRefusalKey(error) }) },
    );
  };

  const resend = (invitation: Invitation) => {
    setInvitationRefusal(null);
    resendInvitation.mutate(invitation.id, {
      // Resending rotates the token, so the new link is the only one that works and the
      // inviter is the only person who can pass it on.
      onSuccess: (updated) => setAcceptLink({ path: updated.accept_path, role: updated.role }),
      onError: (error) =>
        setInvitationRefusal({
          email: invitation.email,
          key: invitationRefusalKey(error, 'resend'),
        }),
    });
  };

  const revoke = (invitation: Invitation) => {
    setInvitationRefusal(null);
    revokeInvitation.mutate(invitation.id, {
      onError: (error) =>
        setInvitationRefusal({
          email: invitation.email,
          key: invitationRefusalKey(error, 'revoke'),
        }),
    });
  };

  return (
    <Stack spacing={2.5}>
      <Stack spacing={0.5}>
        <Typography component="h1" variant="h5">
          {t('members.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('members.subtitle')}
        </Typography>
      </Stack>

      {role !== null && !canManage && (
        <Alert severity="info">{t('members.readOnly', { role: t(`enums.role.${role}`) })}</Alert>
      )}

      <Paper variant="outlined">
        <Stack
          direction="row"
          sx={{ p: 2, alignItems: 'center', justifyContent: 'space-between', gap: 2 }}
        >
          <Typography variant="subtitle1" component="p">
            {t('members.list.title')}
          </Typography>
          {canManage && (
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setInviteOpen(true)}>
              {t('members.invite.action')}
            </Button>
          )}
        </Stack>

        {members.isPending && (
          <Box sx={{ p: 2 }}>
            <ListSkeleton rows={3} />
          </Box>
        )}

        {members.isError && (
          <Box sx={{ p: 2 }}>
            <ErrorPanel error={members.error} onRetry={() => void members.refetch()} />
          </Box>
        )}

        {members.data && (
          <TableContainer>
            <Table size="small" aria-label={t('members.list.title')}>
              <TableHead>
                <TableRow>
                  <TableCell>{t('members.list.columns.email')}</TableCell>
                  <TableCell>{t('members.list.columns.role')}</TableCell>
                  <TableCell>{t('members.list.columns.status')}</TableCell>
                  <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                    {t('members.list.columns.joined')}
                  </TableCell>
                  <TableCell sx={{ textAlign: 'end' }}>
                    {t('members.list.columns.actions')}
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((member) => {
                  const manageable = role !== null && canManageRole(role, member.role);
                  const options = [...grantableRoles(role ?? 'agent')];
                  if (!options.includes(member.role)) {
                    options.push(member.role);
                  }

                  return (
                    <TableRow key={member.id} hover>
                      <TableCell>{member.email}</TableCell>
                      <TableCell>
                        {canManage && manageable ? (
                          <TextField
                            select
                            size="small"
                            id={`member-role-${member.id}`}
                            label={t('members.list.columns.role')}
                            value={member.role}
                            onChange={(event) =>
                              applyMemberChange(member, {
                                role: event.target.value as MembershipRole,
                              })
                            }
                          >
                            {options.map((option) => (
                              <MenuItem key={option} value={option}>
                                {t(`enums.role.${option}`)}
                              </MenuItem>
                            ))}
                          </TextField>
                        ) : (
                          <RoleChip role={member.role} />
                        )}
                      </TableCell>
                      <TableCell>
                        <MemberStatusChip status={member.status} />
                      </TableCell>
                      <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                        <Typography variant="caption" color="text.secondary">
                          {formatDate(member.created_at, locale)}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ textAlign: 'end', whiteSpace: 'nowrap' }}>
                        {canManage && manageable && member.status === 'active' && (
                          <Button
                            size="small"
                            onClick={() => applyMemberChange(member, { status: 'removed' })}
                          >
                            {t('members.actions.revoke')}
                          </Button>
                        )}
                        {canManage && manageable && member.status === 'removed' && (
                          <Button
                            size="small"
                            onClick={() => applyMemberChange(member, { status: 'active' })}
                          >
                            {t('members.actions.restore')}
                          </Button>
                        )}
                        {can(role, 'members.transfer') &&
                          member.status === 'active' &&
                          member.user_id !== callerId && (
                            <Button size="small" onClick={() => setTransferTarget(member)}>
                              {t('members.actions.transfer')}
                            </Button>
                          )}
                      </TableCell>
                    </TableRow>
                  );
                })}
                {memberRefusal && (
                  <TableRow>
                    <TableCell colSpan={5} sx={{ borderBottom: 0 }}>
                      <Alert severity="warning">{t(memberRefusal.key)}</Alert>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>

      {canManage && (
        <Paper variant="outlined">
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            sx={{ p: 2, alignItems: { sm: 'center' }, justifyContent: 'space-between', gap: 1 }}
          >
            <Typography variant="subtitle1" component="p">
              {t('members.invitations.title')}
            </Typography>
            <TextField
              select
              size="small"
              id="invitation-filter"
              label={t('members.invitations.columns.state')}
              value={invitationFilter}
              onChange={(event) => setInvitationFilter(event.target.value as InvitationFilter)}
              sx={{ minWidth: 200 }}
            >
              {INVITATION_FILTERS.map((value) => (
                <MenuItem key={value} value={value}>
                  {t(`members.invitations.filters.${value}`)}
                </MenuItem>
              ))}
            </TextField>
          </Stack>

          {invitationRefusal && (
            <Box sx={{ px: 2, pb: 2 }}>
              <Alert severity="warning">
                {t(invitationRefusal.key)} — {invitationRefusal.email}
              </Alert>
            </Box>
          )}

          {invitations.isPending && (
            <Box sx={{ p: 2 }}>
              <ListSkeleton rows={2} />
            </Box>
          )}

          {invitations.isError && (
            <Box sx={{ p: 2 }}>
              <ErrorPanel error={invitations.error} onRetry={() => void invitations.refetch()} />
            </Box>
          )}

          {invitations.data && invitations.data.results.length === 0 && (
            <Box sx={{ px: 2, pb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                {t('members.invitations.empty')}
              </Typography>
            </Box>
          )}

          {invitations.data && invitations.data.results.length > 0 && (
            <TableContainer>
              <Table size="small" aria-label={t('members.invitations.title')}>
                <TableHead>
                  <TableRow>
                    <TableCell>{t('members.invitations.columns.email')}</TableCell>
                    <TableCell>{t('members.invitations.columns.role')}</TableCell>
                    <TableCell>{t('members.invitations.columns.state')}</TableCell>
                    <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                      {t('members.invitations.columns.created')}
                    </TableCell>
                    <TableCell sx={{ textAlign: 'end' }}>
                      {t('members.invitations.columns.actions')}
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {invitations.data.results.map((invitation) => (
                    <TableRow key={invitation.id} hover>
                      <TableCell>
                        <Typography variant="body2">{invitation.email}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {t(`members.invitations.deliveryStatus.${invitation.delivery_status}`)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <RoleChip role={invitation.role} />
                      </TableCell>
                      <TableCell>
                        <Stack spacing={0.25}>
                          <InvitationStateChip state={invitation.status} />
                          <Typography variant="caption" color="text.secondary">
                            {t('members.invitations.expires', {
                              date: formatRelativeTime(invitation.expires_at, locale),
                            })}
                          </Typography>
                        </Stack>
                      </TableCell>
                      <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                        <Typography variant="caption" color="text.secondary">
                          {formatDate(invitation.created_at, locale)}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ textAlign: 'end', whiteSpace: 'nowrap' }}>
                        {invitation.status !== 'accepted' && (
                          <Button size="small" onClick={() => resend(invitation)}>
                            {t('members.actions.resend')}
                          </Button>
                        )}
                        {invitation.status !== 'accepted' && (
                          <Button size="small" color="inherit" onClick={() => revoke(invitation)}>
                            {t('members.actions.revokeInvitation')}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Paper>
      )}

      {inviteOpen && (
        <InviteMemberDialog
          workspaceId={workspaceId}
          onInvited={(invitation) => {
            setInviteOpen(false);
            setAcceptLink({ path: invitation.accept_path, role: invitation.role });
          }}
          onClose={() => setInviteOpen(false)}
        />
      )}

      {acceptLink && (
        <AcceptLinkDialog
          acceptPath={acceptLink.path}
          role={acceptLink.role}
          onClose={() => setAcceptLink(null)}
        />
      )}

      {transferTarget && (
        <TransferOwnershipDialog
          workspaceId={workspaceId}
          member={transferTarget}
          onClose={() => setTransferTarget(null)}
        />
      )}
    </Stack>
  );
}
