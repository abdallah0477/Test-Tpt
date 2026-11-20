"""Inspection jobs: start a Runner job, wait for DONE, import the result once.

inspections/{ins}/inspection.json is written once, at a terminal status, after
its screenshot and crops (AD-4, AD-5). Its presence means "imported".
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from contracts import (
    DoneData,
    ErrorBody,
    FailedData,
    Inspection,
    InspectionResult,
    InspectionStatus,
    JobDoneEvent,
    JobFailedEvent,
    JobProgressEvent,
    JobQueuedEvent,
    SseEvent,
    new_id,
    utc_now,
)
from pydantic import ValidationError

from app.utils import gates, runner_client, store
from app.utils.config import get_config
from app.v1.inspection.schemas import InspectionStarted

log = logging.getLogger("app.inspection")

POLL_INTERVAL_S = 0.2


@dataclass
class Job:
    job_id: str
    session_id: str
    url: str
    done: asyncio.Event = field(default_factory=asyncio.Event)
    error: ErrorBody | None = None


_jobs: dict[str, Job] = {}
_tasks: set[asyncio.Task] = set()


def inspection_path(inspection_id: str) -> str:
    return f"inspections/{inspection_id}/inspection.json"


def load(inspection_id: str) -> Inspection | None:
    path = inspection_path(inspection_id)
    return Inspection.model_validate(store.read_json(path)) if store.exists(path) else None


def job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


# ---------------------------------------------------------------- start


def _store_failure(job: Job, status: InspectionStatus, reason: str) -> Inspection:
    """A terminal Inspection with no Findings (nothing is invented)."""
    inspection = Inspection(
        inspection_id=job.job_id,
        session_id=job.session_id,
        requested_url=job.url,
        captured_at=utc_now(),
        status=status,
        reason=reason,
    )
    try:
        store.write_once(inspection_path(job.job_id), inspection)
    except store.AlreadyExistsError:
        return load(job.job_id) or inspection
    return inspection


async def start(session_id: str, url: str, *, reinspect: bool = False) -> InspectionStarted:
    """Send a job to the Runner (G0 must already be recorded) and watch for its result."""
    job = Job(job_id=new_id("ins"), session_id=session_id, url=url)
    extra = {"session_id": session_id, "job_id": job.job_id}
    send = runner_client.reinspect if reinspect else runner_client.inspect
    try:
        accepted = await send(session_id, job.job_id, url)  # raises GateError without G0
    except runner_client.RunnerError as exc:
        log.warning("runner unavailable", extra=extra)
        reason = (
            f"The Runner service could not start the inspection ({exc.message}). Possible causes: "
            "the runner container is not running, RUNNER_URL is wrong, or the Runner is restarting."
        )
        inspection = _store_failure(job, InspectionStatus.unreachable, reason)
        return InspectionStarted(
            session_id=session_id,
            inspection_id=job.job_id,
            job_id=job.job_id,
            inspection_status=inspection.status,
        )
    log.info("inspection job accepted", extra=extra)
    _jobs[job.job_id] = job
    task = asyncio.create_task(_watch(job))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return InspectionStarted(
        session_id=session_id,
        inspection_id=job.job_id,
        job_id=job.job_id,
        queue_position=accepted.queue_position,
    )


async def start_new(session_id: str, url: str) -> InspectionStarted:
    """Record G0 for the URL's origin, then start (Story 1.4)."""
    gates.record("G0", session_id, origin=url)
    return await start(session_id, url)


# ---------------------------------------------------------------- watch and import


async def _watch(job: Job) -> None:
    extra = {"session_id": job.session_id, "job_id": job.job_id}
    timeout_ms = get_config().runner.job_timeout_ms
    deadline = time.monotonic() + timeout_ms / 1000
    try:
        while not runner_client.result_ready(job.job_id):
            if time.monotonic() > deadline:
                log.warning("runner job timed out", extra=extra)
                reason = (
                    f"The Runner did not finish within {timeout_ms} ms. Possible causes: a very slow page, "
                    "a long Runner queue, or the Runner stopped."
                )
                _store_failure(job, InspectionStatus.timeout, reason)
                return
            await asyncio.sleep(POLL_INTERVAL_S)
        import_result(job.job_id, expected_session_id=job.session_id)
    except Exception as exc:  # noqa: BLE001 - reported over SSE, never silent
        log.error("inspection import failed", exc_info=exc, extra=extra)
        job.error = ErrorBody(code="import_failed", message="The Runner result could not be imported")
    finally:
        job.done.set()


def _copy_blob(job_id: str, source: str | None, dest: str) -> str | None:
    """Copy a Runner file into data/; returns its path relative to data/, or None if missing."""
    if not source:
        return None
    data = runner_client.read_blob(job_id, source)
    if data is None:
        return None
    try:
        store.write_once(dest, data)
    except store.AlreadyExistsError:
        pass  # an earlier, interrupted import already copied it
    return dest


def import_result(job_id: str, *, expected_session_id: str | None = None) -> Inspection:
    """Import out/{job_id}/ into inspections/{job_id}/ once, then clean up out/{job_id}/."""
    existing = load(job_id)
    if existing is not None:
        runner_client.cleanup(job_id)
        return existing
    try:
        result: InspectionResult = runner_client.read_result(job_id)
    except (OSError, ValueError, ValidationError) as exc:
        raise ValueError(f"invalid result.json for {job_id}") from exc
    inspection = result.inspection
    if inspection.inspection_id != job_id:
        raise ValueError(f"result.json belongs to {inspection.inspection_id}, not {job_id}")
    if expected_session_id is not None and inspection.session_id != expected_session_id:
        raise ValueError(f"result.json of {job_id} names another session")

    base = f"inspections/{job_id}"
    inspection.screenshot = _copy_blob(job_id, inspection.screenshot, f"{base}/screenshot.png")
    for finding in inspection.findings:
        finding.crop = _copy_blob(job_id, finding.crop, f"{base}/crops/{finding.finding_id}.png")
    try:
        store.write_once(inspection_path(job_id), inspection)
    except store.AlreadyExistsError:
        inspection = load(job_id) or inspection
    runner_client.cleanup(job_id)
    log.info("inspection imported", extra={"session_id": inspection.session_id, "inspection_id": job_id})
    return inspection


def recover() -> None:
    """At startup: import results whose DONE arrived while the backend was down."""
    for job_id in runner_client.finished_jobs():
        try:
            import_result(job_id)
        except Exception as exc:  # noqa: BLE001 - one bad folder must not block startup
            log.error("could not recover a Runner result", exc_info=exc, extra={"job_id": job_id})


async def shutdown() -> None:
    for task in list(_tasks):
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _jobs.clear()


# ---------------------------------------------------------------- events


def final_event(job_id: str) -> SseEvent:
    inspection = load(job_id)
    if inspection is not None:
        data = DoneData(result_kind="inspection", result_id=job_id, inspection_status=inspection.status)
        return JobDoneEvent(job_id=job_id, step="import", data=data)
    running = _jobs.get(job_id)
    error = (running.error if running else None) or ErrorBody(
        code="import_failed", message="The Runner result could not be imported"
    )
    return JobFailedEvent(job_id=job_id, step="import", data=FailedData(error=error))


async def events(job: Job) -> AsyncIterator[SseEvent]:
    """Runner queue/progress events for the job, then the backend's own job_done / job_failed.

    The Runner's own job_done/job_failed are not relayed: the job is finished for
    the UI only when the Inspection is stored.
    """
    queue: asyncio.Queue[SseEvent | None] = asyncio.Queue()

    async def relay() -> None:
        try:
            async for event in runner_client.stream_events(job.job_id):
                if isinstance(event, JobQueuedEvent | JobProgressEvent):
                    await queue.put(event)
        except runner_client.RunnerError:
            log.info("runner event stream unavailable", extra={"job_id": job.job_id})

    async def finish() -> None:
        await job.done.wait()
        await queue.put(None)

    tasks = [asyncio.create_task(relay()), asyncio.create_task(finish())]
    try:
        while (event := await queue.get()) is not None:
            yield event
        yield final_event(job.job_id)
    finally:
        for task in tasks:
            task.cancel()
