import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, Transaction } from "../api/client";
import { holdingsQueryKey } from "./useHoldings";

export const transactionsQueryKey = ["transactions"] as const;

export function useTransactions() {
  return useQuery({
    queryKey: transactionsQueryKey,
    queryFn: ({ signal }) => apiGet<Transaction[]>("/transactions", { signal }),
    staleTime: 1000 * 60 * 2,
  });
}

export type CreateTransactionPayload = {
  asset_code: string;
  asset_type: string;
  asset_name?: string;
  operation: string;
  trade_date: string;
  amount: string;
  units?: string;
  price?: string;
  fee: string;
  reason?: string;
};

export function useCreateTransaction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateTransactionPayload) =>
      apiPost<Transaction>("/transactions", payload),
    onSuccess: async () => {
      await Promise.allSettled([
        queryClient.invalidateQueries({ queryKey: transactionsQueryKey }),
        queryClient.invalidateQueries({ queryKey: holdingsQueryKey }),
      ]);
    },
  });
}

export function useRetractTransaction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => apiDelete<{ status: string; id: number }>(`/transactions/${id}`),
    onSuccess: async () => {
      await Promise.allSettled([
        queryClient.invalidateQueries({ queryKey: transactionsQueryKey }),
        queryClient.invalidateQueries({ queryKey: holdingsQueryKey }),
      ]);
    },
  });
}
