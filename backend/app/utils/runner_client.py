"""The only code that talks to the Runner (AD-2, AD-19).

HTTP (base URL = config runner.url):
    health()                           GET  /health      -> bool
    inspect(session_id, job_id, url)   POST /inspect     -> JobAccepted
    reinspect(session_id, job_id, url) POST /reinspect   -> JobAccepted
    close(session_id)                  POST /close
    stream_events(job_id)              GET  /events?job_id=  -> async iterator of contracts SseEvent

Every load first calls gates.require("runner.load_url", ...) and sends
gates.approved_origins(session) as the allow-list (AD-15).

Exchange volume (config runner.exchange_dir), written by the Runner:
    out/{job_id}/result.json, screenshot.png, crops/{finding_id}.png, DONE (last)
Read with result_ready(), read_result(), read_blob(); remove with cleanup().
"""

import logging
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from contracts import InspectionResult, InspectRequest, JobAccepted, SseEvent, is_id, parse_event
from pydantic import ValidationError

from app.utils import gates
from app.utils.config import get_config

log = logging.getLogger("app.runner_client")

# Tests replace this with an httpx.MockTransport (a fake Runner).
transport: httpx.AsyncBaseTransport | None = None

REQUEST_TIMEOUT_S = 10.0
DONE_MARKER = "DONE"
RESULT_FILE = "result.json"


class RunnerError(Exception):
    """The Runner refused or failed a request."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RunnerUnavailableError(RunnerError):
    """The Runner could not be reached at all (connection refused, DNS, timeout)."""


def _client(timeout: httpx.Timeout | float = REQUEST_TIMEOUT_S) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=get_config().runner.url, transport=transport, timeout=timeout)


async def _post(path: str, body: dict) -> httpx.Response:
    try:
        async with _client() as client:
            response = await client.post(path, json=body)
    except httpx.TransportError as exc:
        raise RunnerUnavailableError(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__) from exc
    if response.status_code >= 400:
        raise RunnerError(f"Runner answered {path} with HTTP {response.status_code}", response.status_code)
    return response


async def health() -> bool:
    try:
        async with _client(timeout=3.0) as client:
            response = await client.get("/health")
    except httpx.TransportError:
        return False
    return response.status_code == 200


async def _load(path: str, session_id: str, job_id: str, url: str) -> JobAccepted:
    gates.require("runner.load_url", session_id, url)
    request = InspectRequest(
        job_id=job_id,
        session_id=session_id,
        url=url,
        allowed_origins=gates.approved_origins(session_id),
        load_timeout_ms=get_config().inspection.load_timeout_ms,
    )
    response = await _post(path, request.model_dump(mode="json"))
    try:
        return JobAccepted.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise RunnerError(f"Runner answered {path} with an invalid body") from exc


async def inspect(session_id: str, job_id: str, url: str) -> JobAccepted:
    return await _load("/inspect", session_id, job_id, url)


async def reinspect(session_id: str, job_id: str, url: str) -> JobAccepted:
    """Re-inspect in the Session's long-lived inspection context (manual login, AD-20)."""
    return await _load("/reinspect", session_id, job_id, url)


async def close(session_id: str) -> None:
    await _post("/close", {"session_id": session_id})


async def stream_events(job_id: str) -> AsyncIterator[SseEvent]:
    """Typed events of one job from the Runner's SSE stream. Ends when the stream closes.

    Raises RunnerUnavailableError if the stream can't be opened.
    """
    timeout = httpx.Timeout(REQUEST_TIMEOUT_S, read=None)
    try:
        async with _client(timeout=timeout) as client:
            async with client.stream("GET", "/events", params={"job_id": job_id}) as response:
                if response.status_code >= 400:
                    raise RunnerError(f"Runner answered /events with HTTP {response.status_code}")
                data: list[str] = []
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data.append(line[5:].removeprefix(" "))
                    elif not line.strip() and data:
                        event = _parse("\n".join(data))
                        data = []
                        if event is not None and event.job_id == job_id:
                            yield event
    except httpx.TransportError as exc:
        raise RunnerUnavailableError(str(exc) or type(exc).__name__) from exc


def _parse(raw: str) -> SseEvent | None:
    try:
        return parse_event(raw)
    except ValidationError:
        log.warning("ignored an invalid Runner event")
        return None


# ---------------------------------------------------------------- exchange volume


def _job_dir(job_id: str) -> Path:
    if not (is_id(job_id, "ins") or is_id(job_id, "run")):
        raise ValueError(f"not a job id: {job_id!r}")
    return get_config().runner.exchange_dir / "out" / job_id


def result_ready(job_id: str) -> bool:
    return (_job_dir(job_id) / DONE_MARKER).is_file()


def finished_jobs() -> list[str]:
    """Job ids in out/ whose DONE marker is present."""
    out = get_config().runner.exchange_dir / "out"
    if not out.is_dir():
        return []
    return sorted(p.name for p in out.iterdir() if is_id(p.name, "ins") and (p / DONE_MARKER).is_file())


def read_result(job_id: str) -> InspectionResult:
    """Parse out/{job_id}/result.json. Raises ValueError/ValidationError/OSError if it's missing or invalid."""
    return InspectionResult.model_validate_json((_job_dir(job_id) / RESULT_FILE).read_bytes())


def read_blob(job_id: str, relative: str) -> bytes | None:
    """A file the result points to (path relative to out/{job_id}/); None if missing or outside the job folder."""
    base = _job_dir(job_id).resolve()
    full = (base / relative).resolve()
    if base not in full.parents or not full.is_file():
        return None
    return full.read_bytes()


def cleanup(job_id: str) -> None:
    shutil.rmtree(_job_dir(job_id), ignore_errors=True)
