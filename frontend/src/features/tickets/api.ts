import { apiRequest } from '@/lib/api/client';
import type { Paginated } from '@/lib/api/pagination';
import type { MessageVisibility, TicketPriority, TicketStatus } from '@/lib/domain';

export interface Ticket {
  readonly id: string;
  readonly subject: string;
  readonly description: string;
  readonly status: TicketStatus;
  readonly priority: TicketPriority;
  readonly category: string;
  readonly requester_email: string;
  readonly requester_name: string;
  readonly requester_user_id: string | null;
  readonly assignee_id: string | null;
  readonly version: number;
  readonly first_response_due_at: string | null;
  readonly first_responded_at: string | null;
  readonly resolved_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface TicketListQuery {
  readonly status?: TicketStatus | undefined;
  readonly priority?: TicketPriority | undefined;
  /** `me`, `unassigned`, or a user id — the three forms the contract accepts. */
  readonly assignee?: string | undefined;
  readonly search?: string | undefined;
  readonly ordering?: string | undefined;
  readonly page?: number | undefined;
}

export interface TicketPage extends Paginated<Ticket> {
  readonly pageSize: number;
}

/**
 * Build the query string from the values the contract allows.
 *
 * Empty and undefined parameters are omitted rather than sent blank: the API validates
 * each filter against an enum or a length range, so `?status=` would be a 400 rather
 * than "no filter" (ADR-023).
 */
export function buildTicketQueryString(query: TicketListQuery, pageSize: number): string {
  const params = new URLSearchParams();
  if (query.status) {
    params.set('status', query.status);
  }
  if (query.priority) {
    params.set('priority', query.priority);
  }
  if (query.assignee) {
    params.set('assignee', query.assignee);
  }
  const search = query.search?.trim();
  if (search) {
    params.set('search', search);
  }
  if (query.ordering) {
    params.set('ordering', query.ordering);
  }
  params.set('page', String(query.page ?? 1));
  params.set('page_size', String(pageSize));
  return params.toString();
}

export async function listTickets(
  workspaceId: string,
  query: TicketListQuery,
  pageSize: number,
  signal?: AbortSignal,
): Promise<TicketPage> {
  const page = await apiRequest<Paginated<Ticket>>(
    `/workspaces/${workspaceId}/tickets/?${buildTicketQueryString(query, pageSize)}`,
    { signal },
  );
  return { ...page, pageSize };
}

function ticketPath(workspaceId: string, ticketId: string): string {
  return `/workspaces/${workspaceId}/tickets/${ticketId}/`;
}

/** Only the fields the contract accepts on create; status and assignment are commands. */
export interface TicketCreateInput {
  readonly subject: string;
  readonly description: string;
  readonly requester_email: string;
  readonly requester_name?: string;
  readonly priority?: TicketPriority;
  readonly category?: string;
}

/** The `PATCH` field set; `status` and `assignee_id` are never edited this way. */
export interface TicketFieldEdit {
  readonly subject?: string;
  readonly description?: string;
  readonly priority?: TicketPriority;
  readonly category?: string;
  readonly requester_email?: string;
  readonly requester_name?: string;
}

export async function getTicket(
  workspaceId: string,
  ticketId: string,
  signal?: AbortSignal,
): Promise<Ticket> {
  return apiRequest<Ticket>(ticketPath(workspaceId, ticketId), { signal });
}

export async function createTicket(workspaceId: string, input: TicketCreateInput): Promise<Ticket> {
  return apiRequest<Ticket>(`/workspaces/${workspaceId}/tickets/`, {
    method: 'POST',
    body: input,
  });
}

/**
 * Edit fields under optimistic concurrency: `version` is the one that was read, and a
 * stale value comes back as `409` with the current version in `error.details.version`
 * (ADR-022).
 */
export async function updateTicketFields(
  workspaceId: string,
  ticketId: string,
  edit: TicketFieldEdit,
  version: number,
): Promise<Ticket> {
  return apiRequest<Ticket>(ticketPath(workspaceId, ticketId), {
    method: 'PATCH',
    body: edit,
    ifMatch: version,
  });
}

export async function assignTicket(
  workspaceId: string,
  ticketId: string,
  assigneeId: string | null,
): Promise<Ticket> {
  return apiRequest<Ticket>(`${ticketPath(workspaceId, ticketId)}assign/`, {
    method: 'POST',
    body: { assignee_id: assigneeId },
  });
}

export async function transitionTicket(
  workspaceId: string,
  ticketId: string,
  status: TicketStatus,
): Promise<Ticket> {
  return apiRequest<Ticket>(`${ticketPath(workspaceId, ticketId)}transition/`, {
    method: 'POST',
    body: { status },
  });
}

/** The author is a member of this workspace, or absent for a system-written row. */
export interface MessageAuthor {
  readonly user_id: string;
  readonly email: string;
}

export interface TicketMessage {
  readonly id: string;
  readonly body: string;
  readonly visibility: MessageVisibility;
  readonly author: MessageAuthor | null;
  readonly created_at: string;
}

export async function listMessages(
  workspaceId: string,
  ticketId: string,
  page: number,
  pageSize: number,
  signal?: AbortSignal,
): Promise<Paginated<TicketMessage>> {
  // Messages are append-only and read oldest-first, so the timeline is built from page 1
  // upwards; the contract's `count` tells the screen whether more exist.
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return apiRequest<Paginated<TicketMessage>>(
    `${ticketPath(workspaceId, ticketId)}messages/?${params.toString()}`,
    { signal },
  );
}

/** `visibility` is always sent: the server's default must never decide what a reader sees. */
export async function createMessage(
  workspaceId: string,
  ticketId: string,
  body: string,
  visibility: MessageVisibility,
): Promise<TicketMessage> {
  return apiRequest<TicketMessage>(`${ticketPath(workspaceId, ticketId)}messages/`, {
    method: 'POST',
    body: { body, visibility },
  });
}

/** The four states a background AI job reports (FR-024). */
export const AI_JOB_STATUSES = ['pending', 'running', 'succeeded', 'failed'] as const;
export type AIJobStatus = (typeof AI_JOB_STATUSES)[number];

/** One cited article: an identifier the reader can resolve, and the title to show. */
export interface DraftSource {
  readonly article_id: string;
  readonly title: string;
}

/**
 * A reply draft, exactly as the contract returns it.
 *
 * `requires_human_approval` is always true: the field exists so the screen cannot treat a
 * draft as a sent reply, and it is rendered rather than assumed.
 */
export interface ReplyDraft {
  readonly id: string;
  readonly status: AIJobStatus;
  readonly draft_text: string;
  readonly source_articles: readonly DraftSource[];
  readonly provider: string;
  readonly model: string;
  readonly requires_human_approval: boolean;
  readonly error: string | null;
  readonly created_at: string;
}

/** The classification half of the status read; the panel shows the draft only. */
export interface AIClassification {
  readonly status: AIJobStatus;
  readonly category: string;
  readonly sentiment: string;
  readonly suggested_priority: TicketPriority;
  readonly confidence: number | null;
  readonly rationale: string;
  readonly provider: string;
  readonly model: string;
  readonly created_at: string;
}

export interface AIStatus {
  readonly classification: AIClassification | null;
  readonly draft: ReplyDraft | null;
}

/**
 * Both AI jobs for one ticket, in a single read.
 *
 * Either half may be null: a ticket has a classification before anyone asks for a draft, and
 * an older ticket may have neither.
 */
export async function getAIStatus(
  workspaceId: string,
  ticketId: string,
  signal?: AbortSignal,
): Promise<AIStatus> {
  return apiRequest<AIStatus>(`${ticketPath(workspaceId, ticketId)}ai-status/`, { signal });
}

/**
 * Queue a draft for the ticket's current version, returning the job (`202`).
 *
 * The text arrives later, through the status read: a model call behind this request would
 * make a slow provider visible as a slow screen. A second request while a draft is still
 * running returns that job instead of paying for another.
 */
export async function requestDraft(workspaceId: string, ticketId: string): Promise<ReplyDraft> {
  return apiRequest<ReplyDraft>(`${ticketPath(workspaceId, ticketId)}ai-draft/`, {
    method: 'POST',
    body: {},
  });
}
