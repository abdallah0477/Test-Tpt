"""The single worker thread: a FIFO queue of jobs, run one at a time (AD-19).

Playwright's sync API is used only in this thread. The thread owns the browser
and one long-lived BrowserContext per session_id (AD-20), so a manual login in
the visible browser is still there for /reinspect.

Every context gets a route on "**/*" that aborts requests whose origin is not in
the session's allowed origins (AD-15). The allowed list is replaced by each job.
"""

import logging
import queue
import shutil
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

from contracts import (
    DoneData,
    ErrorBody,
    FailedData,
    Inspection,
    InspectionResult,
    InspectionStatus,
    InspectRequest,
    JobDoneEvent,
    JobFailedEvent,
    JobProgressEvent,
    JobQueuedEvent,
    ProgressData,
    QueuedData,
    utc_now,
)
from playwright.sync_api import sync_playwright

from app import exchange
from app.config import Settings
from app.events import EventBus
from app.inspect_page import JobDeadline, SessionState, inspect, origin_of

log = logging.getLogger("runner")


@dataclass
class Job:
    kind: str  # "inspect", "reinspect" or "close"
    request: Any
    future: Future = field(default_factory=Future)


@dataclass
class SessionContext:
    context: Any
    state: SessionState


class Worker:
    def __init__(self, settings: Settings, bus: EventBus) -> None:
        self.settings = settings
        self.bus = bus
        self._queue: queue.Queue[Job | None] = queue.Queue()
        self._lock = threading.Lock()
        self._waiting: list[str] = []  # job ids queued or running, in order
        self._thread = threading.Thread(target=self._run, name="runner-worker", daemon=True)
        self._browser: Any = None
        self._contexts: dict[str, SessionContext] = {}

    # ---------------------------------------------------------------- called from the API

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 15) -> None:
        self._queue.put(None)
        self._thread.join(timeout)

    def is_known(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._waiting

    def submit_inspect(self, kind: str, request: InspectRequest) -> tuple[int, Future]:
        """Queue an inspection; returns (jobs ahead of it, a future that resolves when it is done)."""
        with self._lock:
            position = len(self._waiting)
            self._waiting.append(request.job_id)
        self.bus.publish(JobQueuedEvent(job_id=request.job_id, step="queued", data=QueuedData(position=position)))
        job = Job(kind, request)
        self._queue.put(job)
        return position, job.future

    def submit_close(self, session_id: str) -> Future:
        job = Job("close", session_id)
        self._queue.put(job)
        return job.future

    def session_ids(self) -> list[str]:
        return sorted(self._contexts)

    # ---------------------------------------------------------------- worker thread

    def _run(self) -> None:
        with sync_playwright() as playwright:
            self._playwright = playwright
            while True:
                job = self._queue.get()
                if job is None:
                    break
                try:
                    if job.kind == "close":
                        job.future.set_result(self._close(job.request))
                    else:
                        self._inspect_job(job)
                        job.future.set_result(True)
                except Exception as error:  # never let one job kill the worker
                    log.exception("job failed")
                    job.future.set_exception(error)
                finally:
                    if job.kind != "close":
                        with self._lock:
                            self._waiting.remove(job.request.job_id)
            for session in list(self._contexts.values()):
                _quietly(session.context.close)
            if self._browser is not None:
                _quietly(self._browser.close)

    def _ensure_browser(self) -> Any:
        if self._browser is None or not self._browser.is_connected():
            self._contexts.clear()  # contexts died with the old browser
            width, height = self.settings.viewport_width, self.settings.viewport_height
            self._browser = self._playwright.chromium.launch(
                headless=self.settings.headless,
                args=["--window-position=0,0", f"--window-size={width},{height + 120}"],
            )
        return self._browser

    def _session(self, session_id: str, allowed_origins: list[str]) -> tuple[SessionContext, bool]:
        """The session's long-lived context, created on first use. Returns (context, reused)."""
        browser = self._ensure_browser()
        allowed = {o for o in (origin_of(x) for x in allowed_origins) if o}
        existing = self._contexts.get(session_id)
        if existing is not None:
            existing.state.allowed = allowed
            return existing, True

        state = SessionState(allowed=allowed)
        context = browser.new_context(
            viewport={"width": self.settings.viewport_width, "height": self.settings.viewport_height},
            device_scale_factor=1,
            locale="en-US",
            timezone_id="UTC",
            service_workers="block",  # a service worker could bypass the route allowlist
        )

        def guard(route: Any, request: Any) -> None:
            origin = origin_of(request.url)
            if origin is None or origin in state.allowed:
                route.continue_()
            else:
                state.blocked.append(origin)
                route.abort("blockedbyclient")

        def guard_socket(ws: Any) -> None:
            if origin_of(ws.url) in state.allowed:
                ws.connect_to_server()
            else:
                state.blocked.append(str(origin_of(ws.url)))
                ws.close()

        context.route("**/*", guard)
        context.route_web_socket("**/*", guard_socket)
        context.set_default_timeout(15000)
        session = SessionContext(context, state)
        self._contexts[session_id] = session
        return session, False

    def _close(self, session_id: str) -> bool:
        session = self._contexts.pop(session_id, None)
        if session is None:
            return False
        _quietly(session.context.close)
        return True

    def _inspect_job(self, job: Job) -> None:
        request: InspectRequest = job.request
        job_id = request.job_id
        out_dir = exchange.job_dir(self.settings.exchange_dir, job_id)
        if out_dir.exists():
            shutil.rmtree(out_dir)  # leftovers of a crashed attempt; DONE was never written
        out_dir.mkdir(parents=True)

        def emit(step: str, message: str) -> None:
            self.bus.publish(JobProgressEvent(job_id=job_id, step=step, data=ProgressData(message=message)))

        log.info("job started", extra={"job_id": job_id, "session_id": request.session_id})
        try:
            session, reused = self._session(request.session_id, request.allowed_origins)
            if job.kind == "reinspect":
                emit("load", "Reusing the session's browser" if reused else "No earlier browser; starting a new one")
            page = session.context.pages[0] if session.context.pages else session.context.new_page()
            result = inspect(
                page,
                job_id=job_id,
                session_id=request.session_id,
                url=request.url,
                load_timeout_ms=request.load_timeout_ms,
                out_dir=out_dir,
                state=session.state,
                emit=emit,
                deadline=JobDeadline(self.settings.job_timeout_ms),
                max_crops=self.settings.max_crops,
            )
        except Exception as error:
            log.exception("inspection crashed", extra={"job_id": job_id})
            # Still write a result and DONE so the backend never waits for nothing.
            result = InspectionResult(
                inspection=Inspection(
                    inspection_id=job_id,
                    session_id=request.session_id,
                    requested_url=request.url,
                    captured_at=utc_now(),
                    status=InspectionStatus.unreachable,
                    reason=f"The Runner failed while inspecting ({type(error).__name__}). Retry the inspection.",
                )
            )
            exchange.write_json(out_dir / "result.json", result)
            exchange.write_done(out_dir)
            body = ErrorBody(code="runner_error", message=f"{type(error).__name__}: {error}"[:500])
            self.bus.publish(JobFailedEvent(job_id=job_id, step="done", data=FailedData(error=body)))
            return

        exchange.write_json(out_dir / "result.json", result)
        exchange.write_done(out_dir)
        status = result.inspection.status
        log.info("job done", extra={"job_id": job_id, "status": status.value})
        self.bus.publish(
            JobDoneEvent(
                job_id=job_id,
                step="done",
                data=DoneData(result_kind="inspection", result_id=job_id, inspection_status=status),
            )
        )


def _quietly(fn: Any) -> None:
    try:
        fn()
    except Exception:
        pass
