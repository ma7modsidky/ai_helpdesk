import { describe, expect, it } from 'vitest';

import { can, canManageRole, grantableRoles, ROLE_CAPABILITIES } from './capabilities';
import { MEMBERSHIP_ROLES } from './domain';

describe('capability mirror', () => {
  it('matches the capability table in the API contract', () => {
    expect(can('owner', 'members.manage')).toBe(true);
    expect(can('admin', 'members.manage')).toBe(true);
    expect(can('manager', 'members.manage')).toBe(false);
    expect(can('agent', 'members.manage')).toBe(false);

    expect(can('manager', 'tickets.assign_others')).toBe(true);
    expect(can('agent', 'tickets.assign_others')).toBe(false);

    // Both of these are owner-only, and the second one is why transfer is separate from
    // member management (ADR-028).
    expect(can('admin', 'members.transfer')).toBe(false);
    expect(can('owner', 'members.transfer')).toBe(true);

    for (const role of MEMBERSHIP_ROLES) {
      // Reading is not mirrored: every member may read any ticket in the workspace, so the
      // UI never has to ask (ADR-021).
      expect(ROLE_CAPABILITIES[role]).not.toContain('tickets.view');
    }
  });

  it('holds nothing when the role is not known yet', () => {
    expect(can(null, 'tickets.comment')).toBe(false);
    expect(can(undefined, 'tickets.comment')).toBe(false);
  });

  it('lets an admin manage roles below their own and nobody at or above it', () => {
    expect(canManageRole('admin', 'manager')).toBe(true);
    expect(canManageRole('admin', 'agent')).toBe(true);
    expect(canManageRole('admin', 'admin')).toBe(false);
    expect(canManageRole('admin', 'owner')).toBe(false);
    expect(canManageRole('owner', 'admin')).toBe(true);
  });

  it('never offers a role at or above the caller, and offers ownership only to the owner', () => {
    expect(grantableRoles('admin')).toEqual(['manager', 'agent']);
    expect(grantableRoles('manager')).toEqual(['agent']);
    expect(grantableRoles('agent')).toEqual([]);
    expect(grantableRoles('owner')).toEqual([...MEMBERSHIP_ROLES]);
  });
});
