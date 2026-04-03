import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "../api/client";
import type { EventSearchRequest } from "../api/types";

export function useEventSearch(req: EventSearchRequest | null) {
  return useQuery({
    queryKey: ["events", "search", req],
    queryFn: () => eventsApi.search(req!),
    enabled: !!req,
  });
}

export function useTimeline(startTime: string, endTime: string, aoiId?: string) {
  return useQuery({
    queryKey: ["events", "timeline", startTime, endTime, aoiId],
    queryFn: () => eventsApi.timeline({
      start_time: startTime,
      end_time: endTime,
      ...(aoiId ? { aoi_id: aoiId } : {}),
    }),
    enabled: !!(startTime && endTime),
  });
}

export function useSources() {
  return useQuery({ queryKey: ["events", "sources"], queryFn: eventsApi.sources });
}