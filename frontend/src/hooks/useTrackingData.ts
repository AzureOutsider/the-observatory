import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, Asset, TrackingHistory } from "../api/client";
import { watchlistsQueryKey } from "./useWatchlists";

export type TrackingItem = {
  id: number;
  watchlist_id: number;
  asset_id: number;
  asset: Asset;
  official_name: string;
  custom_name?: string | null;
  display_name: string;
  tags: string[];
};

export function trackingItemQueryKey(watchlistId?: number, itemId?: number) {
  return ["watchlist-item", watchlistId, itemId] as const;
}

export function useTrackingItem(watchlistId?: number, itemId?: number) {
  return useQuery({
    queryKey: trackingItemQueryKey(watchlistId, itemId),
    queryFn: ({ signal }) => apiGet<TrackingItem>(`/watchlists/${watchlistId}/items/${itemId}`, { signal }),
    enabled: watchlistId != null && itemId != null,
    staleTime: 1000 * 60 * 2,
  });
}

export function trackingHistoryQueryKey(watchlistId?: number, itemId?: number) {
  return ["watchlist-item-history", watchlistId, itemId, "6m"] as const;
}

export function useTrackingHistory(watchlistId?: number, itemId?: number) {
  return useQuery({
    queryKey: trackingHistoryQueryKey(watchlistId, itemId),
    queryFn: ({ signal }) => apiGet<TrackingHistory>(`/watchlists/${watchlistId}/items/${itemId}/history?range=6m`, { signal }),
    enabled: watchlistId != null && itemId != null,
    staleTime: 1000 * 60 * 10,
  });
}

export type UpdateTrackingItemPayload = {
  watchlistId: number;
  itemId: number;
  custom_name: string | null;
  tags: string[];
};

export function useUpdateTrackingItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ watchlistId, itemId, ...payload }: UpdateTrackingItemPayload) =>
      apiPatch<TrackingItem>(`/watchlists/${watchlistId}/items/${itemId}`, payload),
    onSuccess: (item) => {
      queryClient.setQueryData(trackingItemQueryKey(item.watchlist_id, item.id), item);
      void queryClient.invalidateQueries({ queryKey: watchlistsQueryKey });
    },
  });
}

export function useDeleteTrackingItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ watchlistId, itemId }: { watchlistId: number; itemId: number }) =>
      apiDelete<{ status: string; id: number }>(`/watchlists/${watchlistId}/items/${itemId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: watchlistsQueryKey });
    },
  });
}
