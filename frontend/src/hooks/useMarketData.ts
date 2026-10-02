import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, MarketIndex, NewsItem } from "../api/client";

export const marketIndicesQueryKey = ["market", "indices"] as const;

export function useMarketIndices() {
  return useQuery({
    queryKey: marketIndicesQueryKey,
    queryFn: ({ signal }) => apiGet<MarketIndex[]>("/market/indices", { signal }),
    staleTime: 1000 * 60 * 2,
  });
}

export function newsQueryKey(limit: number) {
  return ["news", { limit }] as const;
}

export function useNews(limit = 20) {
  return useQuery({
    queryKey: newsQueryKey(limit),
    queryFn: ({ signal }) => apiGet<NewsItem[]>(`/news?limit=${limit}`, { signal }),
    staleTime: 1000 * 60 * 5,
  });
}

export function useRefreshNews(limit = 20) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => apiGet<NewsItem[]>(`/news?limit=${limit}&refresh=true`),
    onSuccess: (rows) => {
      queryClient.setQueryData(newsQueryKey(limit), rows);
    },
  });
}
