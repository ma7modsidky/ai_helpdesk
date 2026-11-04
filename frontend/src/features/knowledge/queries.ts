import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeyPrefixes, queryKeys } from '@/lib/api/queryKeys';

import {
  ARTICLES_PAGE_SIZE,
  createArticle,
  listArticles,
  reindexArticle,
  setArticleStatus,
  updateArticle,
  type ArticleEdit,
  type ArticleListQuery,
  type ArticleWrite,
  type KnowledgeArticle,
} from './api';

/**
 * Every write invalidates the workspace's article lists and nothing else.
 *
 * A list row carries the lifecycle state, the indexing state, and the chunk count, so a save,
 * a publish, or a reindex changes what it shows. The narrowest correct prefix is the article
 * collection; the ticket screens do not read it.
 */
function useArticleWrite<TVariables>(
  workspaceId: string,
  mutationFn: (variables: TVariables) => Promise<KnowledgeArticle>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.articles(workspaceId) });
    },
  });
}

export function useArticles(workspaceId: string, query: ArticleListQuery) {
  return useQuery({
    queryKey: queryKeys.articles(workspaceId, query),
    queryFn: ({ signal }) => listArticles(workspaceId, query, ARTICLES_PAGE_SIZE, signal),
    enabled: workspaceId.length > 0,
    // Indexing is asynchronous, so the state a screen shows is only as fresh as the last read.
    placeholderData: (previous) => previous,
  });
}

export function useCreateArticle(workspaceId: string) {
  return useArticleWrite<ArticleWrite>(workspaceId, (input) => createArticle(workspaceId, input));
}

export function useUpdateArticle(workspaceId: string) {
  return useArticleWrite<{ articleId: string; edit: ArticleEdit }>(
    workspaceId,
    ({ articleId, edit }) => updateArticle(workspaceId, articleId, edit),
  );
}

export function useSetArticleStatus(workspaceId: string) {
  return useArticleWrite<{ articleId: string; status: 'published' | 'archived' }>(
    workspaceId,
    ({ articleId, status }) => setArticleStatus(workspaceId, articleId, status),
  );
}

export function useReindexArticle(workspaceId: string) {
  return useArticleWrite<string>(workspaceId, (articleId) =>
    reindexArticle(workspaceId, articleId),
  );
}
