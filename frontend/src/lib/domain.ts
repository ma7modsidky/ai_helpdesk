/**
 * The API's closed vocabularies, mirrored for display and for building requests.
 *
 * These are the exact values the contract accepts (`04_API_CONTRACT.md`, and the
 * `TextChoices` in `apps/tickets/models.py` and `apps/organizations/models.py`).
 * They exist so a status chip, a filter list, and a request body cannot disagree.
 * The server validates every one of them; this file never decides what is legal.
 */

export const TICKET_STATUSES = [
  'open',
  'in_progress',
  'waiting_on_customer',
  'resolved',
  'closed',
] as const;
export type TicketStatus = (typeof TICKET_STATUSES)[number];

export const TICKET_PRIORITIES = ['low', 'normal', 'high', 'urgent'] as const;
export type TicketPriority = (typeof TICKET_PRIORITIES)[number];

export const MESSAGE_VISIBILITIES = ['public_reply', 'internal_note'] as const;
export type MessageVisibility = (typeof MESSAGE_VISIBILITIES)[number];

export const MEMBERSHIP_ROLES = ['owner', 'admin', 'manager', 'agent'] as const;
export type MembershipRole = (typeof MEMBERSHIP_ROLES)[number];

export const INVITABLE_ROLES = ['admin', 'manager', 'agent'] as const;

export const INVITATION_STATES = ['pending', 'expired', 'accepted', 'revoked'] as const;
export type InvitationState = (typeof INVITATION_STATES)[number];

/**
 * Ordering values the ticket list accepts. Anything outside this list is a 400,
 * which is why the UI builds its select from the same constant it sends (ADR-023).
 */
export const TICKET_ORDERINGS = [
  '-updated_at',
  'updated_at',
  '-created_at',
  'created_at',
  '-priority',
  'priority',
  '-status',
  'status',
] as const;
export type TicketOrdering = (typeof TICKET_ORDERINGS)[number];

export const DEFAULT_TICKET_ORDERING: TicketOrdering = '-updated_at';
