import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch, Holding, Transaction } from "../api/client";

export const holdingsQueryKey = ["holdings"] as const;

export function useHoldings() {
  return useQuery({
    queryKey: holdingsQueryKey,
    queryFn: ({ signal }) => apiGet<Holding[]>("/holdings", { signal }),
    staleTime: 1000 * 60 * 2,
  });
}

export type HoldingUpdatePayload = {
  custom_name?: string | null;
  amount?: string;
  profit?: string | null;
  units?: string | null;
  cost_basis?: string | null;
  correction_reason?: string;
};

export function useHoldingTransactions(holdingId: number) {
  return useQuery({
    queryKey: [...holdingsQueryKey, holdingId, "transactions"],
    queryFn: ({ signal }) => apiGet<Transaction[]>(`/holdings/${holdingId}/transactions`, { signal }),
    staleTime: 1000 * 60,
  });
}

export function useUpdateHolding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: HoldingUpdatePayload }) =>
      apiPatch<Holding>(`/holdings/${id}`, payload),
    onSuccess: (updated, { payload }) => {
      queryClient.setQueryData<Holding[]>(holdingsQueryKey, (current) =>
        current?.map((holding) => (holding.id === updated.id ? updated : holding)),
      );
      if ("custom_name" in payload) {
        for (const key of ["holdings", "transactions", "watchlists", "watchlist-item", "watchlist-item-history", "agent"]) {
          void queryClient.invalidateQueries({ queryKey: [key] });
        }
      }
    },
  });
}
