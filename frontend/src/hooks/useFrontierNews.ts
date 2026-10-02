import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, NewsItem } from "../api/client";

const frontierNewsLimit = 80;

export const frontierNewsTagsQueryKey = ["frontier-news", "tags"] as const;
export const frontierNewsQueryKey = ["frontier-news", { limit: frontierNewsLimit }] as const;

export function useFrontierNewsTags() {
  return useQuery({
    queryKey: frontierNewsTagsQueryKey,
    queryFn: ({ signal }) => apiGet<string[]>("/frontier-news/tags", { signal }),
    staleTime: 1000 * 60 * 30,
  });
}

export function useFrontierNews() {
  return useQuery({
    queryKey: frontierNewsQueryKey,
    queryFn: ({ signal }) => apiGet<NewsItem[]>(`/frontier-news?limit=${frontierNewsLimit}&refresh=false`, { signal }),
    staleTime: 1000 * 60 * 5,
  });
}

export function useRefreshFrontierNews() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => apiGet<NewsItem[]>(`/frontier-news?limit=${frontierNewsLimit}&refresh=true`),
    onSuccess: (items) => {
      queryClient.setQueryData(frontierNewsQueryKey, items);
    },
  });
}
