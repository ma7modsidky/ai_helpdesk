import { apiRequest } from '@/lib/api/client';
import type { Paginated } from '@/lib/api/pagination';

/** The publication lifecycle, mirrored from the server's enum (FR-030). */
export const ARTICLE_STATUSES = ['draft', 'published', 'archived'] as const;
export type ArticleStatus = (typeof ARTICLE_STATUSES)[number];

/** The four states an indexing job reports (FR-033). */
export const INDEX_STATUSES = ['pending', 'running', 'succeeded', 'failed'] as const;
export type IndexStatus = (typeof INDEX_STATUSES)[number];

/**
 * One article, exactly as the contract returns it.
 *
 * Both states are present on purpose: `status` is what a person chose, `index_status` is what
 * the background job did. A published article whose job failed is live on screen and absent
 * from AI retrieval, and the editor has to say so rather than imply it is in use.
 */
export interface KnowledgeArticle {
  readonly id: string;
  readonly title: string;
  readonly body: string;
  readonly status: ArticleStatus;
  readonly version: number;
  readonly author_id: string | null;
  readonly published_at: string | null;
  readonly archived_at: string | null;
  readonly index_status: IndexStatus;
  readonly indexed_version: number | null;
  readonly index_attempts: number;
  readonly index_error: string;
  readonly indexed_at: string | null;
  /** Chunks of the current version: what retrieval would actually see. */
  readonly chunk_count: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ArticleListQuery {
  readonly status?: ArticleStatus | 'all' | undefined;
  readonly search?: string | undefined;
  readonly page?: number | undefined;
}

export interface ArticlePage extends Paginated<KnowledgeArticle> {
  readonly pageSize: number;
}

export interface ArticleWrite {
  readonly title: string;
  readonly body: string;
}

export interface ArticleEdit {
  readonly title?: string;
  readonly body?: string;
}

export const ARTICLES_PAGE_SIZE = 25;

function articlesPath(workspaceId: string): string {
  return `/workspaces/${workspaceId}/articles/`;
}

/**
 * Build the query string from the values the contract allows.
 *
 * `all` is omitted rather than sent: the server validates `status` against its own enum plus
 * `all`, and an empty value would be a 400 instead of "no filter".
 */
export function buildArticleQueryString(query: ArticleListQuery, pageSize: number): string {
  const params = new URLSearchParams();
  if (query.status && query.status !== 'all') {
    params.set('status', query.status);
  }
  const search = query.search?.trim();
  if (search) {
    params.set('search', search);
  }
  params.set('page', String(query.page ?? 1));
  params.set('page_size', String(pageSize));
  return params.toString();
}

export async function listArticles(
  workspaceId: string,
  query: ArticleListQuery,
  pageSize: number,
  signal?: AbortSignal,
): Promise<ArticlePage> {
  const page = await apiRequest<Paginated<KnowledgeArticle>>(
    `${articlesPath(workspaceId)}?${buildArticleQueryString(query, pageSize)}`,
    { signal },
  );
  return { ...page, pageSize };
}

export async function createArticle(
  workspaceId: string,
  input: ArticleWrite,
): Promise<KnowledgeArticle> {
  return apiRequest<KnowledgeArticle>(articlesPath(workspaceId), {
    method: 'POST',
    body: input,
  });
}

export async function updateArticle(
  workspaceId: string,
  articleId: string,
  edit: ArticleEdit,
): Promise<KnowledgeArticle> {
  return apiRequest<KnowledgeArticle>(`${articlesPath(workspaceId)}${articleId}/`, {
    method: 'PATCH',
    body: edit,
  });
}

/** Publish or archive. Both queue indexing; neither changes the text. */
export async function setArticleStatus(
  workspaceId: string,
  articleId: string,
  status: 'published' | 'archived',
): Promise<KnowledgeArticle> {
  return apiRequest<KnowledgeArticle>(`${articlesPath(workspaceId)}${articleId}/publish/`, {
    method: 'POST',
    body: { status },
  });
}

/** Queue indexing again, including after a failure. */
export async function reindexArticle(
  workspaceId: string,
  articleId: string,
): Promise<KnowledgeArticle> {
  return apiRequest<KnowledgeArticle>(`${articlesPath(workspaceId)}${articleId}/reindex/`, {
    method: 'POST',
    body: {},
  });
}
