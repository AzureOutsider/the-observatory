import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch, Holding } from "../api/client";

export const holdingsQueryKey = ["holdings"] as const;

export function useHoldings() {
  return useQuery({
    queryKey: holdingsQueryKey,
    queryFn: ({ signal }) => apiGet<Holding[]>("/holdings", { signal }),
    staleTime: 1000 * 60 * 2,
  });
}

export type HoldingUpdatePayload = {
  amount?: string;
  profit?: string | null;
  units?: string | null;
  cost_basis?: string | null;
  correction_reason: string;
};

export function useUpdateHolding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: HoldingUpdatePayload }) =>
      apiPatch<Holding>(`/holdings/${id}`, payload),
    onSuccess: (updated) => {
      queryClient.setQueryData<Holding[]>(holdingsQueryKey, (current) =>
        current?.map((holding) => (holding.id === updated.id ? updated : holding)),
      );
    },
  });
}
