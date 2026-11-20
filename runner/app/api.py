"""Runner HTTP API (AD-19). Reachable only on the internal compose network.

    GET  /health            {"status": "ok", ...}
    POST /inspect           InspectRequest -> JobAccepted (202)
    POST /reinspect         InspectRequest -> JobAccepted (202); reuses the session's browser context
    POST /close             CloseRequest -> {"session_id", "closed"}
    GET  /events?job_id=    SSE stream of contracts SseEvent envelopes

Start it with: uvicorn app.api:app --port 8100 --workers 1
"""

import asyncio
from contextlib import asynccontextmanager

from contracts import CloseRequest, InspectRequest, JobAccepted
from fastapi import FastAPI, HTTPException
from sse_starlette import EventSourceResponse

from app import exchange
from app.config import load_settings
from app.events import EventBus
from app.log import setup_logging
from app.worker import Worker

setup_logging()

CLOSE_WAIT_S = 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    (settings.exchange_dir / "out").mkdir(parents=True, exist_ok=True)
    bus = EventBus()
    worker = Worker(settings, bus)
    worker.start()
    app.state.settings, app.state.bus, app.state.worker = settings, bus, worker
    yield
    await asyncio.to_thread(worker.stop)


app = FastAPI(title="Test-Tpt Runner", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "headless": app.state.settings.headless, "sessions": len(app.state.worker.session_ids())}


def _accept(kind: str, request: InspectRequest) -> JobAccepted:
    worker: Worker = app.state.worker
    try:
        out_dir = exchange.job_dir(app.state.settings.exchange_dir, request.job_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if worker.is_known(request.job_id) or out_dir.exists():
        raise HTTPException(409, f"job {request.job_id} already exists")
    position, _ = worker.submit_inspect(kind, request)
    return JobAccepted(job_id=request.job_id, queue_position=position)


@app.post("/inspect", status_code=202)
def inspect(request: InspectRequest) -> JobAccepted:
    return _accept("inspect", request)


@app.post("/reinspect", status_code=202)
def reinspect(request: InspectRequest) -> JobAccepted:
    return _accept("reinspect", request)


@app.post("/close")
def close(request: CloseRequest) -> dict:
    future = app.state.worker.submit_close(request.session_id)
    closed = future.result(timeout=CLOSE_WAIT_S)  # runs in FastAPI's thread pool, not the event loop
    return {"session_id": request.session_id, "closed": closed}


@app.get("/events")
async def events(job_id: str | None = None) -> EventSourceResponse:
    bus: EventBus = app.state.bus
    queue, past = bus.subscribe(job_id)

    async def messages():
        try:
            for event in past:
                yield {"event": event.event, "data": event.model_dump_json()}
            while True:
                event = await queue.get()
                if job_id is None or event.job_id == job_id:
                    yield {"event": event.event, "data": event.model_dump_json()}
        finally:
            bus.unsubscribe(queue)

    return EventSourceResponse(messages(), ping=15)
