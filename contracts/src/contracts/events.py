"""Typed SSE events: envelope {event, job_id, step, status, ts, data} (AD-14).

`SseEvent` is a discriminated union on `event`. Add new event types here and
to the union; the frontend gets them through the OpenAPI schema.
"""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from contracts.ids import utc_now
from contracts.models import ErrorBody, InspectionStatus, Model, UtcDatetime

JobStatus = Literal["queued", "running", "done", "failed"]


class _Envelope(Model):
    job_id: str
    step: str = Field(description="Pipeline step, e.g. 'load', 'extract', 'validate', 'retry'")
    status: JobStatus
    ts: UtcDatetime = Field(default_factory=utc_now)


class QueuedData(Model):
    position: int = Field(ge=0, description="Jobs ahead of this one in the FIFO queue")


class ProgressData(Model):
    message: str
    done: int | None = None
    total: int | None = None


class DoneData(Model):
    result_kind: str = Field(description="e.g. 'inspection', 'response'")
    result_id: str
    inspection_status: InspectionStatus | None = None


class FailedData(Model):
    error: ErrorBody


class JobQueuedEvent(_Envelope):
    event: Literal["job_queued"] = "job_queued"
    status: JobStatus = "queued"
    data: QueuedData


class JobProgressEvent(_Envelope):
    event: Literal["job_progress"] = "job_progress"
    status: JobStatus = "running"
    data: ProgressData


class JobDoneEvent(_Envelope):
    event: Literal["job_done"] = "job_done"
    status: JobStatus = "done"
    data: DoneData


class JobFailedEvent(_Envelope):
    event: Literal["job_failed"] = "job_failed"
    status: JobStatus = "failed"
    data: FailedData


SseEvent = Annotated[
    JobQueuedEvent | JobProgressEvent | JobDoneEvent | JobFailedEvent,
    Field(discriminator="event"),
]

sse_event_adapter: TypeAdapter[SseEvent] = TypeAdapter(SseEvent)


def parse_event(raw: str | bytes) -> SseEvent:
    """Parse one SSE `data:` payload into its typed event."""
    return sse_event_adapter.validate_json(raw)
