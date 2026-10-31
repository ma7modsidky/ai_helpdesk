import InboxOutlinedIcon from '@mui/icons-material/InboxOutlined';
import PeopleOutlinedIcon from '@mui/icons-material/PeopleOutlined';
import type { SvgIconProps } from '@mui/material/SvgIcon';
import type { ElementType } from 'react';

/**
 * The shell's navigation, generated from one table.
 *
 * A route that exists but is missing from the nav is a screen nobody can reach, and a nav
 * entry with no route is a dead link. Keeping both derived from this list removes both
 * failure modes as screens are added (07 §6.3).
 *
 * T4.8 adds the members settings entry and T7.6 the knowledge entry; each lands here at
 * the same time as its route.
 */
export interface WorkspaceNavItem {
  readonly segment: string;
  readonly labelKey: string;
  readonly icon: ElementType<Omit<SvgIconProps, 'ref'>>;
}

/** Settings screens live under one path segment, shared by the nav entry and the route. */
export const MEMBERS_SEGMENT = 'settings/members';

export const WORKSPACE_NAV_ITEMS: readonly WorkspaceNavItem[] = [
  {
    segment: 'inbox',
    labelKey: 'tickets.inbox.title',
    icon: InboxOutlinedIcon,
  },
  {
    segment: MEMBERS_SEGMENT,
    labelKey: 'members.title',
    icon: PeopleOutlinedIcon,
  },
];

export function workspacePath(workspaceId: string, segment: string): string {
  return `/app/${workspaceId}/${segment}`;
}

export const DEFAULT_WORKSPACE_SEGMENT = 'inbox';
