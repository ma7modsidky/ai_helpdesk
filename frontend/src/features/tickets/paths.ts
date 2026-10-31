/**
 * The ticket detail route, built in one place.
 *
 * The inbox links to it, the detail screen reads it, and creating a ticket navigates to it;
 * three copies of the same template is how a route rename leaves one of them broken.
 */
export function ticketPath(workspaceId: string, ticketId: string): string {
  return `/app/${workspaceId}/tickets/${ticketId}`;
}
