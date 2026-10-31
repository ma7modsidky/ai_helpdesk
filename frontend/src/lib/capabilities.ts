/**
 * The capability matrix, mirrored on the client (04 §Tickets, ADR-021).
 *
 * The server decides every request; nothing here authorizes anything. It exists so a
 * control the caller's role cannot use is disabled **with an explanation** instead of
 * being discovered through a 403 (07 §6.4, §6.6), and so the role hierarchy used to offer
 * a change is the same shape as the hierarchy that will refuse it.
 */

import { MEMBERSHIP_ROLES, type MembershipRole } from './domain';

export const CAPABILITIES = [
  'members.manage',
  'members.transfer',
  'invitations.manage',
  'tickets.create',
  'tickets.comment',
  'tickets.edit',
  'tickets.assign_self',
  'tickets.assign_others',
  'tickets.transition',
] as const;

export type Capability = (typeof CAPABILITIES)[number];

const TICKET_CAPABILITIES_FOR_EVERY_ROLE: readonly Capability[] = [
  'tickets.create',
  'tickets.comment',
  'tickets.edit',
  'tickets.assign_self',
  'tickets.transition',
];

export const ROLE_CAPABILITIES: Record<MembershipRole, readonly Capability[]> = {
  owner: [
    ...TICKET_CAPABILITIES_FOR_EVERY_ROLE,
    'tickets.assign_others',
    'members.manage',
    'members.transfer',
    'invitations.manage',
  ],
  admin: [
    ...TICKET_CAPABILITIES_FOR_EVERY_ROLE,
    'tickets.assign_others',
    'members.manage',
    'invitations.manage',
  ],
  manager: [...TICKET_CAPABILITIES_FOR_EVERY_ROLE, 'tickets.assign_others'],
  agent: [...TICKET_CAPABILITIES_FOR_EVERY_ROLE],
};

/**
 * Ordered privileges, highest last — the same ordering as the server's `_ROLE_RANK`.
 *
 * Roles are comparable only through this table: the enum's declaration order is
 * presentation, not authority.
 */
export const ROLE_RANK: Record<MembershipRole, number> = {
  agent: 10,
  manager: 20,
  admin: 30,
  owner: 40,
};

export function isMembershipRole(value: unknown): value is MembershipRole {
  return MEMBERSHIP_ROLES.some((role) => role === value);
}

/** Whether a role holds a capability. A missing role holds nothing. */
export function can(role: MembershipRole | null | undefined, capability: Capability): boolean {
  if (!role) {
    return false;
  }
  return ROLE_CAPABILITIES[role].includes(capability);
}

/**
 * Whether `actor` may change `target`'s role.
 *
 * An admin manages roles strictly below their own and cannot touch a peer or an owner;
 * only an owner may act on an owner (see `change_membership`).
 */
export function canManageRole(actor: MembershipRole, target: MembershipRole): boolean {
  if (actor === 'owner') {
    return true;
  }
  return ROLE_RANK[target] < ROLE_RANK[actor];
}

/**
 * Roles `actor` may grant by a member change: never at or above their own, and only an
 * owner may grant ownership.
 */
export function grantableRoles(actor: MembershipRole): readonly MembershipRole[] {
  return MEMBERSHIP_ROLES.filter((role) => canManageRole(actor, role));
}
