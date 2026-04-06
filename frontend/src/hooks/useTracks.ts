import { useQuery } from "@tanstack/react-query";
import { playbackApi } from "../api/client";
import type { CanonicalEvent } from "../api/types";

/** A track trip in deck.gl TripsLayer format. */
export type TrackWaypoint = [number, number, number, number];

export interface Trip {
  id: string;
  /** Ordered waypoints: [longitude, latitude, unix_seconds, altitude_m] */
  waypoints: TrackWaypoint[];
  entityType: "ship" | "aircraft";
}

const TRACK_QUERY_LIMIT = 4_000;
const AIRCRAFT_MIN_ALTITUDE_M = 3_500;
const MAX_SEGMENT_GAP_SECONDS = 60 * 60;
const MAX_SHIP_STEP_KM = 30;
const MAX_AIRCRAFT_STEP_KM = 350;

function readFiniteNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const num = Number(value);
    if (Number.isFinite(num)) return num;
  }
  return null;
}

function resolveWaypointAltitude(event: CanonicalEvent, entityType: Trip["entityType"]): number {
  if (entityType === "ship") return 0;

  const attrs = (event.attributes ?? {}) as Record<string, unknown>;
  const sourceAltitude = readFiniteNumber(
    event.altitude_m,
    attrs.baro_altitude_m,
    attrs.geo_altitude_m,
    attrs.altitude_m,
  );

  return Math.max(sourceAltitude ?? AIRCRAFT_MIN_ALTITUDE_M, AIRCRAFT_MIN_ALTITUDE_M);
}

function haversineKm(a: TrackWaypoint, b: TrackWaypoint): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b[1] - a[1]);
  const dLon = toRad(b[0] - a[0]);
  const lat1 = toRad(a[1]);
  const lat2 = toRad(b[1]);
  const sinLat = Math.sin(dLat / 2);
  const sinLon = Math.sin(dLon / 2);
  const h = sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLon * sinLon;
  return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(h)));
}

function splitTrackSegments(waypoints: TrackWaypoint[], entityType: Trip["entityType"]): TrackWaypoint[][] {
  if (waypoints.length <= 1) return [waypoints];

  const maxStepKm = entityType === "ship" ? MAX_SHIP_STEP_KM : MAX_AIRCRAFT_STEP_KM;
  const segments: TrackWaypoint[][] = [];
  let current: TrackWaypoint[] = [waypoints[0]];

  for (let i = 1; i < waypoints.length; i += 1) {
    const prev = waypoints[i - 1];
    const next = waypoints[i];
    const dt = next[2] - prev[2];
    const jumpKm = haversineKm(prev, next);
    const shouldBreak = dt > MAX_SEGMENT_GAP_SECONDS || jumpKm > maxStepKm;

    if (shouldBreak) {
      if (current.length > 1) segments.push(current);
      current = [next];
      continue;
    }

    current.push(next);
  }

  if (current.length > 1) segments.push(current);
  return segments;
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
    queryFn: async () => {
      // Demo playback renders denser synthetic telemetry, so keep the replay
      // query comfortably above the seeded point count.
      const response = await playbackApi.query({
        ...(aoiId ? { aoi_id: aoiId } : {}),
        start_time: startTime,
        end_time: endTime,
        source_types: ["telemetry"],
        limit: TRACK_QUERY_LIMIT,
      });

      const entityMap = new Map<
        string,
        { waypoints: TrackWaypoint[]; type: "ship" | "aircraft" }
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
        entityMap.get(event.entity_id)!.waypoints.push([
          lng,
          lat,
          t,
          resolveWaypointAltitude(event, type),
        ]);
      }

      return Array.from(entityMap.entries()).flatMap(([id, data]) => {
        const sorted = data.waypoints.sort((a, b) => a[2] - b[2]);
        const segments = splitTrackSegments(sorted, data.type);
        if (segments.length <= 1) {
          return [{ id, waypoints: sorted, entityType: data.type }];
        }
        return segments.map((segment, index) => ({
          id: `${id}#${index + 1}`,
          waypoints: segment,
          entityType: data.type,
        }));
      });
    },
    // Do not fire until an AOI is selected — an unscoped telemetry query can return
    // a huge unfiltered result set and will 401 on protected deployments.
    enabled: enabled && !!aoiId && !!(startTime && endTime),
    staleTime: 30_000,
  });
}
