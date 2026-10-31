/**
 * The pagination envelope every bounded list uses (04 §Versioning, pagination, and schema).
 *
 * It lives in `lib` rather than in a feature so a second feature can read a list without
 * importing another feature's module.
 */

export interface Paginated<T> {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly T[];
}

/** The contract's maximum page size; workspaces, members, and invitations use it. */
export const PAGE_SIZE = 100;
