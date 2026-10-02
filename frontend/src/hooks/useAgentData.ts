import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AgentResearchContext,
  ReviewAppendResult,
  apiGet,
  apiPost,
} from "../api/client";

export function agentAnalysisQueryKey(topic: string) {
  return ["agent", "analysis-package", topic] as const;
}

export function useAgentAnalysisPackage(topic: string) {
  return useQuery({
    queryKey: agentAnalysisQueryKey(topic),
    queryFn: ({ signal }) => apiGet<AgentResearchContext>(`/agent/analysis-package/today?topic=${encodeURIComponent(topic)}`, { signal }),
    staleTime: 1000 * 60 * 5,
  });
}

export type AppendReviewPayload = {
  analysis_date?: string;
  content: string;
};

export function useAppendReview() {
  return useMutation({
    mutationFn: (payload: AppendReviewPayload) => apiPost<ReviewAppendResult>("/agent/reviews/append", payload),
  });
}
