import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { analyticsApi } from "../api/client";
import type { ReviewDecision } from "../api/types";

export function useReviewQueue(aoiId?: string) {
  return useQuery({
    queryKey: ["analytics", "review", aoiId],
    queryFn: () => analyticsApi.reviewQueue(aoiId),
  });
}

export function useCandidates(jobId: string | null) {
  return useQuery({
    queryKey: ["analytics", "candidates", jobId],
    queryFn: () => analyticsApi.getCandidates(jobId!),
    enabled: !!jobId,
  });
}

export function useSubmitChangeJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ aoiId, startDate, endDate }: { aoiId: string; startDate: string; endDate: string }) =>
      analyticsApi.submitJob(aoiId, startDate, endDate),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analytics"] }),
  });
}

export function useReviewCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, notes }: { id: string; decision: ReviewDecision; notes?: string }) =>
      analyticsApi.review(id, decision, notes),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analytics"] }),
  });
}