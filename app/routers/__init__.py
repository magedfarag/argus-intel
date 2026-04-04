"""FastAPI route sub-modules."""
from app.routers import analyze, config_router, credits, health, jobs, providers_router, search, thumbnails
from app.routers import (
    ws_jobs,
)

__all__ = [
    "health", "config_router", "providers_router",
    "credits", "analyze", "jobs", "search", "ws_jobs",
    "thumbnails",
]
