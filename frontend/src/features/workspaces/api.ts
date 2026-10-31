import { apiRequest } from '@/lib/api/client';
import { PAGE_SIZE, type Paginated } from '@/lib/api/pagination';

export interface Workspace {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  readonly timezone: string;
  readonly status: string;
  readonly created_at: string;
}

export interface CreateWorkspaceInput {
  readonly name: string;
  readonly slug: string;
  readonly timezone: string;
}

export async function listWorkspaces(signal?: AbortSignal): Promise<readonly Workspace[]> {
  const page = await apiRequest<Paginated<Workspace>>(`/workspaces/?page_size=${PAGE_SIZE}`, {
    signal,
  });
  return page.results;
}

export async function createWorkspace(input: CreateWorkspaceInput): Promise<Workspace> {
  return apiRequest<Workspace>('/workspaces/', { method: 'POST', body: input });
}
