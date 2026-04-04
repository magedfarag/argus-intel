import { useQuery } from "@tanstack/react-query";
import { playbackApi } from "../api/client";

/** A track trip in deck.gl TripsLayer format. */
export interface Trip {
  id: string;
  /** Ordered waypoints: [longitude, latitude, unix_seconds] */
  waypoints: [number, number, number][];
  entityType: "ship" | "aircraft";
}

/**
 * P3-3.2 / P3-3.3 — Aggregate telemetry events from the playback API into
 * per-entity trip objects consumable by deck.gl's TripsLayer.
 */
export function useTracks(
  aoiId: string | null,
  startTime: string,
  endTime: string,
  enabled = true,
) {
  return useQuery<Trip[]>({
    queryKey: ["tracks", aoiId, startTime, endTime],
    // Do not fire until an AOI is selected — an unscoped telemetry query can return
    // a huge unfiltered result set and will 401 on protected deployments.
    enabled: enabled && !!aoiId,
    queryFn: async () => {
      const response = await playbackApi.query({
        ...(aoiId ? { aoi_id: aoiId } : {}),
        start_time: startTime,
        end_time: endTime,
        source_types: ["telemetry"],
        limit: 500,
      });

      const entityMap = new Map<
        string,
        { waypoints: [number, number, number][]; type: "ship" | "aircraft" }
      >();

      for (const frame of response.frames) {
        const event = frame.event;
        if (!event.entity_id || event.geometry?.type !== "Point") continue;
        const coords = event.geometry.coordinates as number[];
        const [lng, lat] = coords;
        const t = new Date(event.event_time).getTime() / 1000;
        const type = event.event_type === "ship_position" ? "ship" : "aircraft";
        if (!entityMap.has(event.entity_id)) {
          entityMap.set(event.entity_id, { waypoints: [], type });
        }
        entityMap.get(event.entity_id)!.waypoints.push([lng, lat, t]);
      }

      return Array.from(entityMap.entries()).map(([id, data]) => ({
        id,
        waypoints: data.waypoints.sort((a, b) => a[2] - b[2]),
        entityType: data.type,
      }));
    },
    enabled: enabled && !!(startTime && endTime),
    staleTime: 30_000,
  });
}
