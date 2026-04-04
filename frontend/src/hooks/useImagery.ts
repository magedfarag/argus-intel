import { useQuery } from "@tanstack/react-query";
import { imageryApi } from "../api/client";
import type { ImagerySearchRequest } from "../api/types";

export function useImagerySearch(req: ImagerySearchRequest | null) {
  return useQuery({
    queryKey: ["imagery", "search", req],
    queryFn: () => imageryApi.search(req!),
    enabled: !!req,
  });
}

export function useImageryProviders() {
  return useQuery({
    queryKey: ["imagery", "providers"],
    queryFn: imageryApi.providers,
    refetchInterval: 30_000,
  });
}