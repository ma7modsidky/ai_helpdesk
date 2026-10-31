import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeyPrefixes, queryKeys } from '@/lib/api/queryKeys';
import type { MessageVisibility, TicketStatus } from '@/lib/domain';

import {
  assignTicket,
  createMessage,
  createTicket,
  getTicket,
  listMessages,
  transitionTicket,
  updateTicketFields,
  type Ticket,
  type TicketCreateInput,
  type TicketFieldEdit,
} from './api';

/** A timeline is read as a whole; the contract's maximum page size covers a real ticket. */
export const MESSAGES_PAGE_SIZE = 100;

export function useTicket(workspaceId: string, ticketId: string) {
  return useQuery({
    queryKey: queryKeys.ticket(workspaceId, ticketId),
    queryFn: ({ signal }) => getTicket(workspaceId, ticketId, signal),
    enabled: workspaceId.length > 0 && ticketId.length > 0,
  });
}

export function useTicketMessages(workspaceId: string, ticketId: string) {
  return useQuery({
    queryKey: queryKeys.ticketMessages(workspaceId, ticketId, 1),
    queryFn: ({ signal }) => listMessages(workspaceId, ticketId, 1, MESSAGES_PAGE_SIZE, signal),
    enabled: workspaceId.length > 0 && ticketId.length > 0,
  });
}

/**
 * Every ticket write invalidates the ticket and the workspace's ticket lists.
 *
 * The lists carry status, assignee, and last-update, so a resolve or an assignment changes
 * which rows belong in them and what they show; the narrowest correct set is the ticket
 * itself plus the list prefix (07 §7.3). The updated representation is written straight
 * into the cache, because the contract returns it (04 §Commands).
 */
function useTicketWrite<TVariables>(
  workspaceId: string,
  ticketId: string,
  mutationFn: (variables: TVariables) => Promise<Ticket>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (ticket) => {
      queryClient.setQueryData(queryKeys.ticket(workspaceId, ticketId), ticket);
      void queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.tickets(workspaceId) });
    },
  });
}

export function useCreateTicket(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: TicketCreateInput) => createTicket(workspaceId, input),
    onSuccess: (ticket) => {
      // The new row belongs in the queue the user came from, and the detail screen can
      // render it without a second read.
      queryClient.setQueryData(queryKeys.ticket(workspaceId, ticket.id), ticket);
      void queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.tickets(workspaceId) });
    },
  });
}

export function useUpdateTicketFields(workspaceId: string, ticketId: string) {
  return useTicketWrite(
    workspaceId,
    ticketId,
    ({ edit, version }: { edit: TicketFieldEdit; version: number }) =>
      updateTicketFields(workspaceId, ticketId, edit, version),
  );
}

export function useAssignTicket(workspaceId: string, ticketId: string) {
  return useTicketWrite(workspaceId, ticketId, (assigneeId: string | null) =>
    assignTicket(workspaceId, ticketId, assigneeId),
  );
}

export function useTransitionTicket(workspaceId: string, ticketId: string) {
  return useTicketWrite(workspaceId, ticketId, (status: TicketStatus) =>
    transitionTicket(workspaceId, ticketId, status),
  );
}

export function useAddMessage(workspaceId: string, ticketId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ body, visibility }: { body: string; visibility: MessageVisibility }) =>
      createMessage(workspaceId, ticketId, body, visibility),
    onSuccess: () => {
      // A message moves the ticket's `updated_at` without changing its version, so the
      // conversation and the ticket are both refreshed rather than patched by hand.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.ticketMessages(workspaceId, ticketId, 1),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.ticket(workspaceId, ticketId),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.tickets(workspaceId) });
    },
  });
}
