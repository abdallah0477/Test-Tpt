"""Inspections: start, read, export, blobs, progress events, retry and re-inspect.

Stories 1.4, 1.7, 1.10, 1.11. Credentials are never accepted, logged or stored:
URLs with a user/password part are rejected.
"""

import re
from urllib.parse import urlsplit

from contracts import Inspection, SseEvent, is_id
from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from app.utils import gates, store
from app.utils.errors import ApiError
from app.utils.events import event_response
from app.v1.inspection import jobs
from app.v1.inspection.schemas import InspectionStarted, ReinspectRequest, StartInspectionRequest

router = APIRouter(prefix="/api/v1/inspection", tags=["inspection"])

MAX_URL_LENGTH = 2048
_FINDING_ID = re.compile(r"^f_\d{3,}$")
_SSE_RESPONSES = {200: {"description": "SSE stream of SseEvent", "content": {"text/event-stream": {}}}}
_PNG = {200: {"description": "PNG image", "content": {"image/png": {}}}}


def _valid_url(raw: str) -> str:
    url = raw.strip()
    if not url or len(url) > MAX_URL_LENGTH:
        raise ApiError(422, "invalid_url", "enter an http or https URL")
    try:
        gates.origin_of(url)
        parts = urlsplit(url)
    except ValueError as exc:
        raise ApiError(422, "invalid_url", "enter a valid http or https URL with a host") from exc
    if parts.username is not None or parts.password is not None:
        raise ApiError(
            422, "invalid_url", "URLs with a user name or password are not accepted; sign in by hand in the browser"
        )
    if any(c.isspace() for c in url):
        raise ApiError(422, "invalid_url", "the URL contains spaces")
    return url


def _require_session(session_id: str) -> None:
    if not is_id(session_id, "ses") or not store.exists(f"sessions/{session_id}/session.json"):
        raise ApiError(404, "session_not_found", f"session {session_id} does not exist")


def _get(inspection_id: str) -> Inspection:
    inspection = jobs.load(inspection_id) if is_id(inspection_id, "ins") else None
    if inspection is None:
        raise ApiError(404, "inspection_not_found", f"inspection {inspection_id} is not stored")
    return inspection


def _latest(session_id: str) -> Inspection | None:
    """Latest stored Inspection of a Session (ins_ ids sort by creation time)."""
    for name in reversed(store.list_dir("inspections")):
        if is_id(name, "ins"):
            inspection = jobs.load(name)
            if inspection is not None and inspection.session_id == session_id:
                return inspection
    return None


@router.post("", response_model=InspectionStarted, status_code=202)
async def start_inspection(body: StartInspectionRequest) -> InspectionStarted:
    """Validate the URL, record G0 for its origin and send the job to the Runner."""
    url = _valid_url(body.url)
    _require_session(body.session_id)
    return await jobs.start_new(body.session_id, url)


@router.get("/current", response_model=Inspection)
def current_inspection(session_id: str = Query()) -> Inspection:
    _require_session(session_id)
    inspection = _latest(session_id)
    if inspection is None:
        raise ApiError(404, "inspection_not_found", "this session has no stored inspection yet")
    return inspection


@router.post("/reinspect", response_model=InspectionStarted, status_code=202)
async def reinspect(body: ReinspectRequest) -> InspectionStarted:
    """Inspect again in the Session's long-lived context, e.g. after a manual login (Story 1.11)."""
    _require_session(body.session_id)
    last = _latest(body.session_id)
    if last is None:
        raise ApiError(409, "no_inspection", "start an inspection before re-inspecting")
    return await jobs.start(body.session_id, last.requested_url, reinspect=True)


@router.get("/events/{job_id}", response_model=SseEvent, responses=_SSE_RESPONSES)
async def inspection_events(job_id: str):
    """Progress of one job: job_queued / job_progress from the Runner, then job_done or job_failed."""
    if not is_id(job_id, "ins"):
        raise ApiError(404, "job_not_found", f"unknown job {job_id}")
    running = jobs.job(job_id)
    if running is not None:
        return event_response(jobs.events(running))
    if jobs.load(job_id) is None:
        raise ApiError(404, "job_not_found", f"unknown job {job_id}")

    async def stored():
        yield jobs.final_event(job_id)

    return event_response(stored())


@router.get("/{inspection_id}", response_model=Inspection)
def get_inspection(inspection_id: str) -> Inspection:
    return _get(inspection_id)


@router.get("/{inspection_id}/export", response_model=Inspection)
def export_inspection(inspection_id: str) -> JSONResponse:
    inspection = _get(inspection_id)
    return JSONResponse(
        content=inspection.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{inspection_id}.json"'},
    )


@router.get("/{inspection_id}/screenshot", response_class=Response, responses=_PNG)
def screenshot(inspection_id: str) -> Response:
    inspection = _get(inspection_id)
    if not inspection.screenshot:
        raise ApiError(404, "screenshot_not_found", "this inspection has no screenshot")
    return Response(content=store.read_bytes(inspection.screenshot), media_type="image/png")


@router.get("/{inspection_id}/crops/{finding_id}", response_class=Response, responses=_PNG)
def crop(inspection_id: str, finding_id: str) -> Response:
    inspection = _get(inspection_id)
    finding = next((f for f in inspection.findings if f.finding_id == finding_id), None)
    if not _FINDING_ID.match(finding_id) or finding is None or not finding.crop:
        raise ApiError(404, "crop_not_found", f"no crop for {finding_id}")
    return Response(content=store.read_bytes(finding.crop), media_type="image/png")


@router.post("/{inspection_id}/retry", response_model=InspectionStarted, status_code=202)
async def retry(inspection_id: str) -> InspectionStarted:
    """A new Inspection of the same URL in the same Session (Story 1.10); the old one is unchanged."""
    previous = _get(inspection_id)
    return await jobs.start(previous.session_id, previous.requested_url)
