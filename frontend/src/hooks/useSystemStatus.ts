import { useQuery } from "@tanstack/react-query";
import { apiGet, SystemStatus } from "../api/client";

export const systemStatusQueryKey = ["system", "status"] as const;

export function useSystemStatus() {
  return useQuery({
    queryKey: systemStatusQueryKey,
    queryFn: ({ signal }) => apiGet<SystemStatus>("/system/status", { signal }),
    staleTime: 1000 * 30,
    retry: 1,
  });
}
