"""HTTP API: /health, /inspect, /reinspect, /close, /events (Story 1.2 API side)."""

import json
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCHANGE_DIR", str(tmp_path / "exchange"))
    monkeypatch.setenv("RUNNER_HEADLESS", "true")
    from app.api import app

    with TestClient(app) as c:
        yield c


def wait_done(tmp_path, job_id, timeout=60):
    done = tmp_path / "exchange" / "out" / job_id / "DONE"
    end = time.monotonic() + timeout
    while not done.exists():
        assert time.monotonic() < end, "job did not finish"
        time.sleep(0.1)
    return done.parent


def body(job_id, url, origin, session_id="ses_api"):
    return {"job_id": job_id, "session_id": session_id, "url": url, "allowed_origins": [origin]}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200 and response.json()["status"] == "ok"


def test_inspect_writes_result_and_streams_events(client, tmp_path, base_url):
    response = client.post("/inspect", json=body("ins_api1", base_url + "/login.html", base_url))
    assert response.status_code == 202
    assert response.json() == {"job_id": "ins_api1", "queue_position": 0}
    out = wait_done(tmp_path, "ins_api1")
    assert json.loads((out / "result.json").read_text())["inspection"]["status"] == "complete"

    # Late subscribers get the job's events replayed; stop reading at job_done.
    events = []
    with client.stream("GET", "/events", params={"job_id": "ins_api1"}) as stream:
        for line in stream.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
                if events[-1]["event"] == "job_done":
                    break
    assert events[0]["event"] == "job_queued" and events[-1]["event"] == "job_done"
    assert {e["job_id"] for e in events} == {"ins_api1"}
    assert set(events[0]) == {"event", "job_id", "step", "status", "ts", "data"}

    duplicate = client.post("/inspect", json=body("ins_api1", base_url + "/login.html", base_url))
    assert duplicate.status_code == 409


def test_reinspect_and_close(client, tmp_path, base_url):
    assert client.post("/inspect", json=body("ins_api2", base_url + "/whoami", base_url, "ses_c")).status_code == 202
    wait_done(tmp_path, "ins_api2")
    assert client.post("/reinspect", json=body("ins_api3", base_url + "/whoami", base_url, "ses_c")).status_code == 202
    wait_done(tmp_path, "ins_api3")
    assert client.post("/close", json={"session_id": "ses_c"}).json() == {"session_id": "ses_c", "closed": True}


def test_rejects_unsafe_job_id(client, base_url):
    response = client.post("/inspect", json=body("../escape", base_url + "/login.html", base_url))
    assert response.status_code == 422
