import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, PaperPosition, PaperQuote, PaperTrade, PaperTradeCreate } from "../api/client";

export const paperPortfolioQueryKey = ["paper", "portfolio"] as const;
export const paperHistoryQueryKey = (assetId: number) => ["paper", "asset", assetId, "trades"] as const;

export function usePaperPortfolio() {
  return useQuery({
    queryKey: paperPortfolioQueryKey,
    queryFn: ({ signal }) => apiGet<PaperPosition[]>("/paper/portfolio", { signal }),
    staleTime: 1000 * 60,
  });
}

export function usePaperHistory(assetId: number) {
  return useQuery({
    queryKey: paperHistoryQueryKey(assetId),
    queryFn: ({ signal }) => apiGet<PaperTrade[]>(`/paper/assets/${assetId}/trades`, { signal }),
    staleTime: 1000 * 60,
  });
}

export function usePaperQuotes(assetId: number) {
  return useQuery({
    queryKey: [...paperHistoryQueryKey(assetId), "quotes"],
    queryFn: ({ signal }) => apiGet<PaperQuote[]>(`/paper/assets/${assetId}/quotes`, { signal }),
    staleTime: 1000 * 60,
  });
}

export function useRefreshPaperQuotes() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ updated: number; failed: number }>("/paper/refresh", {}),
    onSuccess: () => client.invalidateQueries({ queryKey: ["paper"] }),
  });
}

export function usePaperTrade() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: PaperTradeCreate) => apiPost<PaperTrade>("/paper/trades", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["paper"] }),
  });
}

export function useRetractPaperTrade() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiDelete<{ status: string; id: number }>(`/paper/trades/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["paper"] }),
  });
}
