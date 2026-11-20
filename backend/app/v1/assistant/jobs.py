"""Background assistant jobs with replayable SSE progress (AD-14).

Steps: building_prompt -> calling_model -> validating -> retry_N -> ... -> done
(job_done, data.result_kind "response", data.result_id = response_id) or job_failed
(error.code model_unavailable | model_error | internal_error). No model tokens are streamed.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

from contracts import (
    DoneData,
    ErrorBody,
    FailedData,
    JobDoneEvent,
    JobFailedEvent,
    JobProgressEvent,
    ProgressData,
    SseEvent,
)

from app.utils import agent_loop, model_client

log = logging.getLogger("app.assistant")


@dataclass
class Job:
    job_id: str
    session_id: str
    events: list[SseEvent] = field(default_factory=list)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    finished: bool = False

    def emit(self, event: SseEvent) -> None:
        self.events.append(event)
        self.finished = self.finished or event.event in ("job_done", "job_failed")
        changed, self.changed = self.changed, asyncio.Event()
        changed.set()

    def progress(self, step: str, message: str, done: int | None, total: int | None) -> None:
        self.emit(
            JobProgressEvent(job_id=self.job_id, step=step, data=ProgressData(message=message, done=done, total=total))
        )


_jobs: dict[str, Job] = {}
_tasks: set[asyncio.Task] = set()

Runner = Callable[[Job], Awaitable[agent_loop.LoopResult]]


def job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def _failed(job: Job, code: str, message: str) -> None:
    job.emit(
        JobFailedEvent(job_id=job.job_id, step="done", data=FailedData(error=ErrorBody(code=code, message=message)))
    )


async def _run(job: Job, runner: Runner) -> None:
    extra = {"session_id": job.session_id, "job_id": job.job_id}
    try:
        result = await runner(job)
    except model_client.ModelUnavailableError as exc:
        log.warning("model unavailable", extra=extra)
        _failed(job, "model_unavailable", str(exc))
    except model_client.ModelError as exc:
        log.warning("model error", extra=extra)
        _failed(job, "model_error", str(exc))
    except Exception as exc:  # noqa: BLE001 - reported over SSE, never silent
        log.error("assistant job failed", exc_info=exc, extra=extra)
        _failed(job, "internal_error", "the assistant job failed")
    else:
        data = DoneData(result_kind="response", result_id=result.response.response_id)
        job.emit(JobDoneEvent(job_id=job.job_id, step="done", data=data))


def start(session_id: str, runner: Runner) -> Job:
    new = Job(job_id=agent_loop.allocate_response_id(), session_id=session_id)
    _jobs[new.job_id] = new
    task = asyncio.create_task(_run(new, runner))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return new


async def events(job: Job) -> AsyncIterator[SseEvent]:
    """Every event of the job so far, then new ones, until job_done / job_failed."""
    index = 0
    while True:
        waiter = job.changed
        while index < len(job.events):
            event = job.events[index]
            index += 1
            yield event
            if event.event in ("job_done", "job_failed"):
                return
        await waiter.wait()


async def shutdown() -> None:
    for task in list(_tasks):
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _jobs.clear()
