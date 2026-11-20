"""v1/session + v1/inspection against a fake Runner (httpx.MockTransport).

The fake writes out/{job_id}/result.json, screenshot.png, crops/ and DONE (last),
as the real Runner does (AD-19).
"""

import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest
from contracts import (
    Inspection,
    InspectRequest,
    JobProgressEvent,
    JobQueuedEvent,
    ProgressData,
    QueuedData,
    parse_event,
)
from fastapi.testclient import TestClient

from app.main import app
from app.utils import gates, runner_client, store
from app.utils.config import get_config
from app.utils.gates import GateError
from app.v1.inspection import jobs
from tests.samples import PNG, sample_result


class FakeRunner:
    def __init__(self, exchange: Path):
        self.exchange = exchange
        self.requests: list[tuple[str, dict]] = []
        self.write_result = True
        self.status = "complete"
        self.down = False

    def write(self, req: InspectRequest) -> None:
        out = self.exchange / "out" / req.job_id
        (out / "crops").mkdir(parents=True)
        result = sample_result(req.job_id, req.session_id, req.url, self.status)
        (out / "result.json").write_text(result.model_dump_json())
        (out / "screenshot.png").write_bytes(PNG)
        (out / "crops" / "f_001.png").write_bytes(PNG + b"crop")
        (out / "DONE").write_text("")

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("connection refused", request=request)
        path = request.url.path
        if path in ("/inspect", "/reinspect"):
            body = json.loads(request.content)
            self.requests.append((path, body))
            req = InspectRequest.model_validate(body)
            if self.write_result:
                self.write(req)
            return httpx.Response(202, json={"job_id": req.job_id, "queue_position": 0})
        if path == "/close":
            self.requests.append((path, json.loads(request.content)))
            return httpx.Response(200, json={})
        if path == "/events":
            job_id = request.url.params["job_id"]
            events = [
                JobQueuedEvent(job_id=job_id, step="queue", data=QueuedData(position=0)),
                JobProgressEvent(job_id=job_id, step="load", data=ProgressData(message="loading page")),
                JobProgressEvent(job_id="ins_other", step="load", data=ProgressData(message="not mine")),
            ]
            text = "".join(f"event: {e.event}\ndata: {e.model_dump_json()}\n\n" for e in events)
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)


@pytest.fixture
def runner(tmp_path, monkeypatch):
    fake = FakeRunner(tmp_path / "exchange")
    monkeypatch.setattr(runner_client, "transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(jobs, "POLL_INTERVAL_S", 0.01)
    return fake


@pytest.fixture
def client(runner):
    with TestClient(app) as c:
        yield c


def new_session(client) -> str:
    response = client.post("/api/v1/session")
    assert response.status_code == 201
    return response.json()["session_id"]


def wait_stored(client, inspection_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/inspection/{inspection_id}")
        if response.status_code == 200:
            return response.json()
        time.sleep(0.02)
    raise AssertionError(f"{inspection_id} was never stored")


def start(client, session_id: str, url: str = "http://localhost:5000/login") -> dict:
    response = client.post("/api/v1/inspection", json={"session_id": session_id, "url": url})
    assert response.status_code == 202, response.text
    return response.json()


# ---------------------------------------------------------------- session


def test_create_and_get_session(client):
    session_id = new_session(client)
    response = client.get(f"/api/v1/session/{session_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id and body["rev"] == 1 and body["inspection_ids"] == []
    assert response.headers["etag"] == "1"
    assert client.get("/api/v1/session/ses_nope").json()["error"]["code"] == "session_not_found"


def test_close_session_calls_runner(client, runner):
    session_id = new_session(client)
    assert client.post(f"/api/v1/session/{session_id}/close").status_code == 204
    assert runner.requests == [("/close", {"session_id": session_id})]


# ---------------------------------------------------------------- start (Story 1.4)


@pytest.mark.parametrize(
    "url", ["ftp://example.com/", "not a url", "http://", "javascript:alert(1)", "", "http://user:pw@example.com/"]
)
def test_invalid_url_creates_nothing(client, runner, data_dir, url):
    session_id = new_session(client)
    before = sorted(p.relative_to(data_dir) for p in data_dir.rglob("*"))
    response = client.post("/api/v1/inspection", json={"session_id": session_id, "url": url})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_url"
    assert sorted(p.relative_to(data_dir) for p in data_dir.rglob("*")) == before
    assert gates.approved_origins(session_id) == []
    assert runner.requests == []


def test_unknown_session_is_404_and_records_nothing(client, runner):
    response = client.post("/api/v1/inspection", json={"session_id": "ses_missing", "url": "http://a.test/"})
    assert response.status_code == 404 and response.json()["error"]["code"] == "session_not_found"
    assert runner.requests == []


def test_valid_url_records_g0_and_returns_ids(client, runner):
    session_id = new_session(client)
    body = start(client, session_id, "http://LocalHost:80/login?x=1")
    assert body["session_id"] == session_id
    assert body["inspection_id"].startswith("ins_") and body["job_id"] == body["inspection_id"]
    assert gates.approved_origins(session_id) == ["http://localhost"]
    path, sent = runner.requests[0]
    assert path == "/inspect"
    assert sent["job_id"] == body["job_id"] and sent["allowed_origins"] == ["http://localhost"]
    assert sent["load_timeout_ms"] == get_config().inspection.load_timeout_ms
    wait_stored(client, body["inspection_id"])


# ---------------------------------------------------------------- import and persistence (Story 1.7)


def test_import_writes_inspection_once_and_copies_blobs(client, runner, data_dir, tmp_path):
    session_id = new_session(client)
    ins = start(client, session_id)["inspection_id"]
    stored = wait_stored(client, ins)

    assert stored["status"] == "complete"
    assert stored["screenshot"] == f"inspections/{ins}/screenshot.png"
    assert stored["findings"][0]["crop"] == f"inspections/{ins}/crops/f_001.png"
    assert stored["findings"][1]["crop"] is None
    assert stored["findings"][0]["locators"][0]["expr"] == 'page.get_by_label("Password")'
    assert (data_dir / stored["screenshot"]).read_bytes() == PNG
    assert not (tmp_path / "exchange" / "out" / ins).exists()  # cleaned up

    with pytest.raises(store.AlreadyExistsError):
        store.write_once(f"inspections/{ins}/inspection.json", {})

    assert client.get(f"/api/v1/inspection/{ins}/screenshot").content == PNG
    crop = client.get(f"/api/v1/inspection/{ins}/crops/f_001")
    assert crop.status_code == 200 and crop.headers["content-type"] == "image/png"
    assert client.get(f"/api/v1/inspection/{ins}/crops/f_002").status_code == 404
    assert client.get(f"/api/v1/inspection/{ins}/crops/..%2F..%2Fsecret").status_code == 404

    current = client.get("/api/v1/inspection/current", params={"session_id": session_id})
    assert current.json()["inspection_id"] == ins
    listing = client.get(f"/api/v1/session/{session_id}/inspections").json()
    assert [i["inspection_id"] for i in listing] == [ins] and listing[0]["counts"]["total"] == 2
    assert client.get(f"/api/v1/session/{session_id}").json()["inspection_ids"] == [ins]


def test_inspection_reloads_identically_after_restart(runner):
    with TestClient(app) as client:
        session_id = new_session(client)
        ins = start(client, session_id)["inspection_id"]
        before = wait_stored(client, ins)
        screenshot = client.get(f"/api/v1/inspection/{ins}/screenshot").content
        listing = client.get(f"/api/v1/session/{session_id}/inspections").json()
    # shutdown dropped the in-memory job state; only data/ survives
    get_config.cache_clear()

    with TestClient(app) as restarted:
        assert jobs.job(ins) is None
        assert restarted.get(f"/api/v1/inspection/{ins}").json() == before
        assert restarted.get(f"/api/v1/inspection/{ins}/screenshot").content == screenshot
        assert restarted.get(f"/api/v1/session/{session_id}/inspections").json() == listing


def test_startup_imports_results_finished_while_down(runner, tmp_path):
    session_id = store.update_json("sessions/ses_x/session.json", lambda _: {"session_id": "ses_x"}, 0)["session_id"]
    job_id = "ins_01JD0000000000000000000000"
    runner.write(InspectRequest(job_id=job_id, session_id=session_id, url="http://a.test/", allowed_origins=[]))
    with TestClient(app) as c:
        assert c.get(f"/api/v1/inspection/{job_id}").json()["status"] == "complete"


def test_export_is_valid_inspection_json(client, runner):
    session_id = new_session(client)
    ins = start(client, session_id)["inspection_id"]
    stored = wait_stored(client, ins)
    response = client.get(f"/api/v1/inspection/{ins}/export")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == f'attachment; filename="{ins}.json"'
    exported = Inspection.model_validate_json(response.content)
    assert exported.model_dump(mode="json") == stored
    assert exported.requested_url and exported.final_url and exported.captured_at


# ---------------------------------------------------------------- failures (Story 1.10)


def test_runner_unreachable_stores_unreachable_with_reason(client, runner):
    runner.down = True
    session_id = new_session(client)
    body = start(client, session_id)
    assert body["inspection_status"] == "unreachable"
    stored = client.get(f"/api/v1/inspection/{body['inspection_id']}").json()
    assert stored["status"] == "unreachable" and "Runner" in stored["reason"]
    assert stored["findings"] == [] and stored["screenshot"] is None
    events = read_events(client, body["job_id"])
    assert [e.event for e in events] == ["job_done"]
    assert events[0].data.inspection_status == "unreachable"


def test_job_timeout_stores_timeout(client, runner, monkeypatch):
    monkeypatch.setenv("TPT__RUNNER__JOB_TIMEOUT_MS", "100")
    get_config.cache_clear()
    runner.write_result = False
    session_id = new_session(client)
    stored = wait_stored(client, start(client, session_id)["inspection_id"])
    assert stored["status"] == "timeout" and stored["findings"] == []


def test_invalid_result_emits_job_failed(client, runner, tmp_path):
    runner.write_result = False
    session_id = new_session(client)
    job_id = start(client, session_id)["job_id"]
    out = tmp_path / "exchange" / "out" / job_id
    out.mkdir(parents=True)
    (out / "result.json").write_text("{not json")
    (out / "DONE").write_text("")
    events = read_events(client, job_id)
    assert events[-1].event == "job_failed" and events[-1].data.error.code == "import_failed"
    assert client.get(f"/api/v1/inspection/{job_id}").status_code == 404


def test_retry_creates_new_inspection(client, runner):
    runner.status = "partial"
    session_id = new_session(client)
    first = start(client, session_id, "https://example.com/a")["inspection_id"]
    original = wait_stored(client, first)
    response = client.post(f"/api/v1/inspection/{first}/retry")
    assert response.status_code == 202
    second = response.json()["inspection_id"]
    assert second != first
    assert wait_stored(client, second)["requested_url"] == "https://example.com/a"
    assert client.get(f"/api/v1/inspection/{first}").json() == original
    assert gates.approved_origins(session_id) == ["https://example.com"]


# ---------------------------------------------------------------- re-inspect (Story 1.11)


def test_reinspect_leaves_old_inspection_unchanged(client, runner):
    runner.status = "login_required"
    session_id = new_session(client)
    first = start(client, session_id)["inspection_id"]
    original = wait_stored(client, first)
    runner.status = "complete"
    response = client.post("/api/v1/inspection/reinspect", json={"session_id": session_id})
    assert response.status_code == 202
    second = response.json()["inspection_id"]
    assert runner.requests[-1][0] == "/reinspect" and runner.requests[-1][1]["url"] == original["requested_url"]
    assert wait_stored(client, second)["status"] == "complete"
    assert client.get(f"/api/v1/inspection/{first}").json() == original
    current = client.get("/api/v1/inspection/current", params={"session_id": session_id}).json()
    assert current["inspection_id"] == second


def test_reinspect_without_inspection_is_409(client):
    session_id = new_session(client)
    response = client.post("/api/v1/inspection/reinspect", json={"session_id": session_id})
    assert response.status_code == 409 and response.json()["error"]["code"] == "no_inspection"


# ---------------------------------------------------------------- gates (AD-15)


def test_gate_blocks_unapproved_origin(runner):
    with pytest.raises(GateError):
        asyncio.run(runner_client.inspect("ses_x", "ins_01JD0000000000000000000000", "http://evil.test/"))
    gates.record("G0", "ses_x", origin="http://ok.test")
    with pytest.raises(GateError):
        asyncio.run(runner_client.reinspect("ses_x", "ins_01JD0000000000000000000000", "http://evil.test/"))
    assert runner.requests == []


def test_runner_client_sends_approved_origins(runner):
    gates.record("G0", "ses_x", origin="http://a.test/x")
    gates.record("G0", "ses_x", origin="https://b.test:8443/")
    runner.write_result = False
    accepted = asyncio.run(runner_client.inspect("ses_x", "ins_01JD0000000000000000000000", "http://a.test/y"))
    assert accepted.queue_position == 0
    assert runner.requests[0][1]["allowed_origins"] == ["http://a.test", "https://b.test:8443"]
    assert asyncio.run(runner_client.health()) is True


# ---------------------------------------------------------------- SSE


def read_events(client, job_id: str) -> list:
    events = []
    with client.stream("GET", f"/api/v1/inspection/events/{job_id}") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data:"):
                events.append(parse_event(line[5:].strip()))
    return events


def test_sse_relays_runner_events_then_job_done(client, runner):
    session_id = new_session(client)
    job_id = start(client, session_id)["job_id"]
    events = read_events(client, job_id)
    assert [e.event for e in events] == ["job_queued", "job_progress", "job_done"]
    assert all(e.job_id == job_id for e in events)
    done = events[-1].data
    assert done.result_kind == "inspection" and done.result_id == job_id and done.inspection_status == "complete"
    assert client.get(f"/api/v1/inspection/{job_id}").status_code == 200


def test_sse_unknown_job_is_404(client):
    assert client.get("/api/v1/inspection/events/ins_01JD0000000000000000000000").status_code == 404
    assert client.get("/api/v1/inspection/events/../x").status_code == 404


def test_openapi_exposes_inspection_models(client):
    schema = client.get("/openapi.json").json()
    assert {"Inspection", "Finding", "LocatorCandidate", "Session", "InspectionStarted", "InspectionSummary"} <= (
        schema["components"]["schemas"].keys()
    )
    assert "/api/v1/inspection/events/{job_id}" in schema["paths"]
