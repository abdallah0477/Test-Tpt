import json
import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import app
from app.utils import gates, store
from app.utils.config import REPO_ROOT, load_config
from app.utils.log import JsonFormatter

# test-only routes to check that errors map onto the AD-14 envelope
_test_routes = APIRouter(prefix="/_test")


@_test_routes.post("/conflict")
def _conflict():
    store.update_json("sessions/ses_t/session.json", lambda s: s, expected_rev=0)
    store.update_json("sessions/ses_t/session.json", lambda s: s, expected_rev=0)


@_test_routes.post("/gate")
def _gate():
    gates.require("runner.load_url", "ses_t", "http://localhost:9/")


app.include_router(_test_routes)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model"]["reachable"] is False and body["model"]["model"]


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_stale_rev_maps_to_409(client):
    response = client.post("/_test/conflict")
    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "rev_conflict" and body["details"] == {"expected_rev": 0, "current_rev": 1}


def test_gate_error_maps_to_403(client):
    response = client.post("/_test/gate")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "gate_not_satisfied"


def test_openapi_exposes_sse_union_and_error_envelope(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert {"SseEvent", "JobProgressEvent", "ErrorEnvelope", "ErrorBody", "Health"} <= schemas.keys()
    assert schemas["SseEvent"]["discriminator"]["propertyName"] == "event"


def test_config_defaults_from_repo_config_toml():
    config = load_config(env={})
    assert config.assistant.max_retries == 2
    assert config.models.assistant.model == "qwen3:4b-instruct-2507-q4_K_M"
    assert config.models.assistant.think is False and config.models.assistant.num_ctx == 8192
    assert config.models.codegen.model == "qwen3:4b-instruct-2507-q4_K_M"
    assert config.cloud.enabled is False
    assert config.ollama.base_url == "http://host.docker.internal:11434"
    assert config.storage.data_dir == REPO_ROOT / "data"
    assert config.inspection.load_timeout_ms > 0 and 0 < config.clarification.threshold <= 1


def test_config_env_overrides(tmp_path):
    env = {
        "DATA_DIR": str(tmp_path / "d"),
        "OLLAMA_BASE_URL": "http://172.17.0.1:11434",
        "RUNNER_URL": "http://localhost:8001",
        "CLOUD_ENABLED": "true",
        "TPT__INSPECTION__LOAD_TIMEOUT_MS": "45000",
        "TPT__MODELS__CODEGEN__NUM_CTX": "4096",
    }
    config = load_config(env=env)
    assert config.storage.data_dir == tmp_path / "d"
    assert config.ollama.base_url == "http://172.17.0.1:11434"
    assert config.runner.url == "http://localhost:8001"
    assert config.cloud.enabled is True
    assert config.inspection.load_timeout_ms == 45000
    assert config.models.codegen.num_ctx == 4096
    assert config.models.assistant.model == "qwen3:4b-instruct-2507-q4_K_M"


def test_json_log_line():
    record = logging.LogRecord("app", logging.INFO, __file__, 1, "hello %s", ("x",), None)
    record.session_id = "ses_1"
    line = json.loads(JsonFormatter().format(record))
    assert line["msg"] == "hello x" and line["session_id"] == "ses_1" and line["ts"].endswith("Z")


def test_to_sse_uses_contract_envelope():
    from contracts import JobProgressEvent, parse_event

    from app.utils.events import to_sse

    event = JobProgressEvent(job_id="ins_1", step="extract", data={"message": "3 of 10", "done": 3, "total": 10})
    message = to_sse(event)
    assert message["event"] == "job_progress"
    assert parse_event(message["data"]) == event
