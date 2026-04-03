"""Export router — P1-5.

POST /api/v1/exports          — generate CSV or GeoJSON export
GET  /api/v1/exports/:job_id  — download the generated file

License-aware filtering is enforced server-side: events whose license
marks redistribution as \u201cnot-allowed\u201d are silently excluded from exports.
The response header ``X-Export-Count`` carries the final included count.
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.models.event_search import EventSearchRequest
from src.services.event_store import EventStore
from src.services.export_service import ExportJob, ExportJobStore, ExportService, get_job_store
from src.services.parquet_export import ParquetExportService

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])

# ── Dependencies ──────────────────────────────────────────────────────────────────

# Singleton event store — reuse the same instance as the events router
from src.api.events import get_event_store

_job_store_instance = get_job_store()


def _get_job_store() -> ExportJobStore:
    return _job_store_instance


def _get_export_service(
    event_store: Annotated[EventStore, Depends(get_event_store)],
    job_store: Annotated[ExportJobStore, Depends(_get_job_store)],
) -> ExportService:
    return ExportService(event_store=event_store, job_store=job_store)


JobStoreDep = Annotated[ExportJobStore, Depends(_get_job_store)]
ServiceDep = Annotated[ExportService, Depends(_get_export_service)]


# ── Request / Response models ───────────────────────────────────────────────────────


class ExportRequest(BaseModel):
    """Request body for POST /api/v1/exports."""
    search: EventSearchRequest = Field(..., description="Search parameters to scope the export")
    format: Literal["csv", "geojson", "parquet"] = Field(
        default="geojson", description="Output format. Use 'parquet' for DuckDB offline analysis."
    )
    include_restricted: bool = Field(
        default=False,
        description="Include events with redistribution=not-allowed (requires elevated role in future)",
    )


class ExportJobResponse(BaseModel):
    """Metadata returned after creating an export job."""
    job_id: str
    status: str
    format: str
    event_count: int
    download_url: str
    error: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ExportJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a CSV or GeoJSON export of search results",
)
def create_export(
    req: ExportRequest,
    service: ServiceDep,
) -> ExportJobResponse:
    """Export canonical events filtered by the supplied search parameters.

    The export is generated synchronously (suitable for up to ~50 k events).
    License-restricted events are excluded unless ``include_restricted=true``
    is explicitly supplied.

    Returns a job record with a ``download_url`` for retrieving the file.
    """
    if req.search.end_time <= req.search.start_time:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")

    # P2-4.1: Parquet export uses ParquetExportService directly
    if req.format == "parquet":
        events = service._events.search(req.search)
        try:
            parquet_svc = ParquetExportService()
            result = parquet_svc.export_events(
                events.events,
                aoi_id=req.search.aoi_id,
                include_restricted=req.include_restricted,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Parquet export failed: {exc}")
        # Store as a standard ExportJob so download_url endpoint works
        from uuid import uuid4
        job_id = str(uuid4())
        job = ExportJob(job_id=job_id, format_="parquet", event_count=result.event_count)
        job.status = "completed"
        job.payload = result.parquet_bytes
        service._jobs.put(job)
        return ExportJobResponse(
            job_id=job_id,
            status="completed",
            format="parquet",
            event_count=result.event_count,
            download_url=f"/api/v1/exports/{job_id}",
        )

    job = service.create_export(
        search_request=req.search,
        format_=req.format,
        include_restricted=req.include_restricted,
    )
    if job.status == "failed":
        raise HTTPException(status_code=500, detail=job.error or "Export generation failed")

    return ExportJobResponse(
        job_id=job.job_id,
        status=job.status,
        format=job.format,
        event_count=job.event_count,
        download_url=f"/api/v1/exports/{job.job_id}",
        error=job.error,
    )


@router.get(
    "/{job_id}",
    summary="Download a previously generated export file",
    response_class=Response,
)
def download_export(job_id: str, job_store: JobStoreDep) -> Response:
    """Stream the generated CSV or GeoJSON file back to the caller.

    The file is served with a ``Content-Disposition: attachment`` header so
    browsers trigger a download.  The job is retained in memory for
    ``_JOB_TTL_SECONDS`` (default 1 hour) then evicted.
    """
    job: ExportJob | None = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found or expired")
    if job.status != "completed" or job.payload is None:
        raise HTTPException(status_code=409, detail=f"Export is not ready (status={job.status})")

    if job.format == "csv":
        media_type = "text/csv"
        filename = f"export_{job_id}.csv"
    elif job.format == "parquet":
        media_type = "application/octet-stream"
        filename = f"export_{job_id}.parquet"
    else:
        media_type = "application/geo+json"
        filename = f"export_{job_id}.geojson"

    return Response(
        content=job.payload,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Count": str(job.event_count),
        },
    )

