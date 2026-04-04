import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { aoisApi } from "../api/client";
import type { CreateAoiRequest } from "../api/types";

export function useAois() {
  return useQuery({ queryKey: ["aois"], queryFn: aoisApi.list });
}

export function useAoi(id: string | null) {
  return useQuery({
    queryKey: ["aois", id],
    queryFn: () => aoisApi.get(id!),
    enabled: !!id,
  });
}

export function useCreateAoi() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateAoiRequest) => aoisApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["aois"] }),
  });
}

export function useDeleteAoi() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => aoisApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["aois"] }),
  });
}