"""Request/response-only models of v1/inspection (never stored)."""

from contracts import InspectionStatus
from contracts.models import Model
from pydantic import Field


class StartInspectionRequest(Model):
    """Never put credentials in the URL; they are rejected (FR-7)."""

    session_id: str = Field(description="From POST /api/v1/session")
    url: str = Field(description="http(s) URL to inspect")


class ReinspectRequest(Model):
    session_id: str


class InspectionStarted(Model):
    session_id: str
    inspection_id: str
    job_id: str = Field(description="Same as inspection_id; subscribe to /api/v1/inspection/events/{job_id}")
    queue_position: int | None = Field(default=None, description="Jobs ahead in the Runner queue")
    inspection_status: InspectionStatus | None = Field(
        default=None, description="Set when the Inspection is already stored (e.g. Runner unreachable)"
    )
