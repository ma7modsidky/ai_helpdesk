import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { queryKeyPrefixes, queryKeys } from '@/lib/api/queryKeys';
import type { MessageVisibility, TicketStatus } from '@/lib/domain';

import {
  assignTicket,
  createMessage,
  createTicket,
  getAIStatus,
  getTicket,
  listMessages,
  requestDraft,
  transitionTicket,
  updateTicketFields,
  type AIStatus,
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

/**
 * Poll cadence and cap for an AI job (T4.4: polling is opt-in, bounded, and stops at a
 * terminal state). Four seconds is slow enough not to hammer a worker and fast enough that a
 * finished draft appears while the agent is still looking at the screen; 60 polls bounds a
 * stuck job at four minutes, after which the panel offers a manual refresh instead.
 */
export const AI_POLL_INTERVAL_MS = 4000;
export const AI_MAX_POLLS = 60;

/**
 * The ticket's AI state, polled only while a draft is pending or running.
 *
 * The poll is keyed separately from the ticket, so waiting for a draft never refetches the
 * conversation, and it stops on `succeeded` or `failed` without further requests. The counter
 * resets whenever a different job id appears, which is what keeps a regenerate from inheriting
 * the previous attempt's budget.
 */
export function useTicketAIStatus(workspaceId: string, ticketId: string) {
  const polls = useRef(0);
  const query = useQuery({
    queryKey: queryKeys.ticketAIStatus(workspaceId, ticketId),
    queryFn: ({ signal }) => getAIStatus(workspaceId, ticketId, signal),
    enabled: workspaceId.length > 0 && ticketId.length > 0,
    refetchInterval: (current) => {
      // Either half can be in flight: classification is queued by ticket creation, a draft by
      // a person, so the same read keeps both fresh and stops when both are terminal.
      const draftStatus = current.state.data?.draft?.status;
      const classificationStatus = current.state.data?.classification?.status;
      const active =
        draftStatus === 'pending' ||
        draftStatus === 'running' ||
        classificationStatus === 'pending' ||
        classificationStatus === 'running';
      if (!active) {
        return false;
      }
      if (polls.current >= AI_MAX_POLLS) {
        return false;
      }
      polls.current += 1;
      return AI_POLL_INTERVAL_MS;
    },
  });

  const draftId = query.data?.draft?.id ?? null;
  useEffect(() => {
    polls.current = 0;
  }, [draftId]);

  return query;
}

/**
 * Queue a draft for this ticket. The response is a job (`202`), not text.
 *
 * Writing the job straight into the cache means the panel switches to its queued state on the
 * same tick as the click, while the poll takes over from there.
 */
export function useRequestDraft(workspaceId: string, ticketId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => requestDraft(workspaceId, ticketId),
    onSuccess: (job) => {
      queryClient.setQueryData<AIStatus>(
        queryKeys.ticketAIStatus(workspaceId, ticketId),
        (previous) => ({ classification: previous?.classification ?? null, draft: job }),
      );
    },
  });
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
