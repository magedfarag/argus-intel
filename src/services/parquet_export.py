"""Parquet export service — P2-4.1.

Converts a list of CanonicalEvents to a DuckDB-Spatial-compatible Apache Parquet
file, suitable for offline analyst workflows.

DuckDB compatibility notes:
- Geometry column is stored as WKT string; use ST_GeomFromText(geometry_wkt) in DuckDB.
- quality_flags and attributes are stored as JSON strings.
- All timestamps are ISO-8601 strings in UTC.

Usage::
    from src.services.parquet_export import ParquetExportService, ParquetExportResult
    svc = ParquetExportService()
    result = svc.export_events(events, aoi_id="pilot-riyadh")
    # result.parquet_bytes contains the raw .parquet file
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

# ── Optional import guard ────────────────────────────────────────────────────

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    _PYARROW_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYARROW_AVAILABLE = False


class ParquetExportError(Exception):
    """Raised when Parquet serialisation fails."""


class ParquetExportResult:
    """Container for a completed Parquet export."""

    def __init__(
        self,
        parquet_bytes: bytes,
        event_count: int,
        aoi_id: Optional[str],
        exported_at: datetime,
    ) -> None:
        self.parquet_bytes = parquet_bytes
        self.event_count = event_count
        self.aoi_id = aoi_id
        self.exported_at = exported_at

    @property
    def size_bytes(self) -> int:
        return len(self.parquet_bytes)


# ── GeoJSON → WKT helpers ─────────────────────────────────────────────────────

def _geojson_point_to_wkt(geojson: Dict[str, Any]) -> str:
    """Convert a GeoJSON Point dict to WKT string."""
    try:
        coords = geojson["coordinates"]
        if not coords or len(coords) < 2:
            return "POINT (0 0)"
        lon, lat = coords[0], coords[1]
        return f"POINT ({lon} {lat})"
    except (KeyError, IndexError, TypeError):
        return "POINT (0 0)"


def _geojson_to_wkt(geojson: Dict[str, Any]) -> str:
    """Best-effort GeoJSON → WKT conversion for common geometry types."""
    gtype = (geojson or {}).get("type", "")
    try:
        if gtype == "Point":
            return _geojson_point_to_wkt(geojson)
        if gtype == "Polygon":
            rings = geojson["coordinates"]
            ring_str = ", ".join(f"{c[0]} {c[1]}" for c in rings[0])
            return f"POLYGON (({ring_str}))"
        if gtype == "MultiPolygon":
            polygons = []
            for poly in geojson["coordinates"]:
                ring_str = ", ".join(f"{c[0]} {c[1]}" for c in poly[0])
                polygons.append(f"({ring_str})")
            return f"MULTIPOLYGON ({', '.join(polygons)})"
    except (KeyError, IndexError, TypeError):
        pass
    return f"GEOMETRYCOLLECTION EMPTY"


def _centroid_coords(geojson: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    """Extract (lon, lat) from a GeoJSON Point dict."""
    try:
        coords = geojson["coordinates"]
        return float(coords[0]), float(coords[1])
    except (KeyError, IndexError, TypeError):
        return None, None


# ── Canonical event → flat row ───────────────────────────────────────────────

def _event_to_row(event: Any) -> Dict[str, Any]:
    """Flatten a CanonicalEvent to a dict of scalar/string values."""
    centroid_lon, centroid_lat = _centroid_coords(event.centroid)
    return {
        "event_id": event.event_id,
        "source": event.source,
        "source_type": event.source_type.value if hasattr(event.source_type, "value") else str(event.source_type),
        "entity_type": event.entity_type.value if hasattr(event.entity_type, "value") else str(event.entity_type),
        "entity_id": event.entity_id or "",
        "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
        "event_time": event.event_time.isoformat() if event.event_time else "",
        "time_start": event.time_start.isoformat() if event.time_start else "",
        "time_end": event.time_end.isoformat() if event.time_end else "",
        "ingested_at": event.ingested_at.isoformat() if event.ingested_at else "",
        "geometry_wkt": _geojson_to_wkt(event.geometry),
        "centroid_lon": centroid_lon if centroid_lon is not None else 0.0,
        "centroid_lat": centroid_lat if centroid_lat is not None else 0.0,
        "confidence": event.confidence if event.confidence is not None else -1.0,
        "quality_flags": json.dumps(event.quality_flags),
        "attributes": json.dumps(event.attributes),
        "license_access_tier": (event.license.access_tier if event.license else "public"),
        "license_redistribution": (event.license.redistribution if event.license else "check-provider-terms"),
        "normalization_warnings": json.dumps(
            event.normalization.normalization_warnings if event.normalization else []
        ),
        "provenance_raw_source_ref": (
            event.provenance.raw_source_ref if event.provenance else ""
        ),
    }


# ── PyArrow schema ────────────────────────────────────────────────────────────

def _build_schema() -> "pa.Schema":
    return pa.schema([
        pa.field("event_id", pa.string()),
        pa.field("source", pa.string()),
        pa.field("source_type", pa.string()),
        pa.field("entity_type", pa.string()),
        pa.field("entity_id", pa.string()),
        pa.field("event_type", pa.string()),
        pa.field("event_time", pa.string()),
        pa.field("time_start", pa.string()),
        pa.field("time_end", pa.string()),
        pa.field("ingested_at", pa.string()),
        pa.field("geometry_wkt", pa.string()),
        pa.field("centroid_lon", pa.float64()),
        pa.field("centroid_lat", pa.float64()),
        pa.field("confidence", pa.float64()),
        pa.field("quality_flags", pa.string()),
        pa.field("attributes", pa.string()),
        pa.field("license_access_tier", pa.string()),
        pa.field("license_redistribution", pa.string()),
        pa.field("normalization_warnings", pa.string()),
        pa.field("provenance_raw_source_ref", pa.string()),
    ])


# ── Service ───────────────────────────────────────────────────────────────────

class ParquetExportService:
    """Converts CanonicalEvents to DuckDB-compatible Parquet bytes.

    Requires pyarrow (installed with the `storage` extra).
    """

    def export_events(
        self,
        events: Sequence[Any],
        aoi_id: Optional[str] = None,
        include_restricted: bool = False,
    ) -> ParquetExportResult:
        """Serialize *events* to Parquet.

        Args:
            events: Sequence of CanonicalEvent instances.
            aoi_id: Optional AOI identifier recorded in metadata.
            include_restricted: When False (default) events with
                ``license.redistribution == 'not-allowed'`` are excluded.

        Returns:
            ParquetExportResult with `.parquet_bytes` ready to write to disk or S3.

        Raises:
            ParquetExportError: If pyarrow is unavailable or serialisation fails.
        """
        if not _PYARROW_AVAILABLE:
            raise ParquetExportError(
                "pyarrow is required for Parquet export. Install with: pip install pyarrow"
            )

        filtered = [
            e for e in events
            if include_restricted or (
                not e.license or e.license.redistribution != "not-allowed"
            )
        ]

        rows = [_event_to_row(e) for e in filtered]
        exported_at = datetime.now(timezone.utc)

        if not rows:
            log.info("ParquetExportService: 0 events after license filter — writing empty table")
            table = pa.table({f.name: [] for f in _build_schema()}, schema=_build_schema())
        else:
            col_data: Dict[str, list] = {f.name: [] for f in _build_schema()}
            for row in rows:
                for col in col_data:
                    col_data[col].append(row.get(col))
            schema = _build_schema()
            arrays = [pa.array(col_data[f.name], type=f.type) for f in schema]
            table = pa.table(arrays, schema=schema)

        try:
            buf = pa.BufferOutputStream()
            pq.write_table(
                table,
                buf,
                compression="snappy",
                write_statistics=True,
            )
            parquet_bytes = buf.getvalue().to_pybytes()
        except Exception as exc:
            raise ParquetExportError(f"Parquet serialisation failed: {exc}") from exc

        log.info(
            "ParquetExportService: exported %d events, %d bytes (aoi=%s)",
            len(filtered),
            len(parquet_bytes),
            aoi_id,
        )
        return ParquetExportResult(
            parquet_bytes=parquet_bytes,
            event_count=len(filtered),
            aoi_id=aoi_id,
            exported_at=exported_at,
        )
