import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, Watchlist } from "../api/client";

export const watchlistsQueryKey = ["watchlists"] as const;

export function useWatchlists() {
  return useQuery({
    queryKey: watchlistsQueryKey,
    queryFn: ({ signal }) => apiGet<Watchlist[]>("/watchlists", { signal }),
    staleTime: 1000 * 60 * 2,
  });
}

export type AddWatchlistItemPayload = {
  watchlistId: number;
  asset_code: string;
  asset_type: "stock" | "fund";
  asset_name?: string;
};

export function useAddWatchlistItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ watchlistId, ...payload }: AddWatchlistItemPayload) =>
      apiPost<{ id: number }>(`/watchlists/${watchlistId}/items`, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: watchlistsQueryKey });
    },
  });
}
