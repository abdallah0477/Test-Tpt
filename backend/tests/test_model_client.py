"""Story 3.1: model_client against a fake Ollama, plus one live test (RUN_OLLAMA_TESTS=1)."""

import asyncio
import json
import os
import time

import httpx
import pytest
from contracts import ModelCallRecord
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import app
from app.utils import model_client, store
from app.utils.config import get_config

MODEL = "qwen3:4b-instruct-2507-q4_K_M"


class FakeOllama:
    def __init__(self, capabilities=("completion", "thinking")):
        self.capabilities = list(capabilities)
        self.chats: list[dict] = []
        self.active = 0
        self.max_active = 0

    async def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.16"})
        if path == "/api/show":
            return httpx.Response(200, json={"capabilities": self.capabilities})
        if path == "/api/chat":
            body = json.loads(request.content)
            self.chats.append(body)
            if not body["messages"]:
                return httpx.Response(200, json={"model": body["model"], "done": True, "message": {"content": ""}})
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return httpx.Response(
                200,
                json={
                    "model": body["model"],
                    "message": {"role": "assistant", "content": '{"answer": "ok"}'},
                    "done": True,
                    "prompt_eval_count": 120,
                    "eval_count": 30,
                    "load_duration": 50_000_000,
                    "total_duration": 450_000_000,
                },
            )
        return httpx.Response(404)


class Answer(BaseModel):
    answer: str


@pytest.fixture
def ollama(monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(model_client, "transport", httpx.MockTransport(fake.handler))
    monkeypatch.setenv("TPT__OLLAMA__HARDWARE", "RTX 3060 Laptop 6GB")
    get_config.cache_clear()
    return fake


def ask(**kwargs):
    return model_client.call(
        "assistant",
        [{"role": "user", "content": "hi"}],
        Answer.model_json_schema(),
        session_id="ses_x",
        feature="test",
        **kwargs,
    )


def test_call_uses_chat_with_schema_and_measures(ollama):
    async def go():
        await model_client.startup()
        return await ask(inspection_id="ins_x", response_id="resp_x")

    call = asyncio.run(go())
    body = ollama.chats[-1]
    assert body["format"] == Answer.model_json_schema() and body["stream"] is False
    assert body["think"] is False  # sent only because /api/show lists "thinking"
    assert body["keep_alive"] == "30m" and body["options"]["num_ctx"] == 8192 and body["model"] == MODEL
    assert call.content == '{"answer": "ok"}'
    assert (call.prompt_tokens, call.completion_tokens, call.load_ms, call.response_ms) == (120, 30, 50, 400)
    assert call.total_ms == 450 and call.setup == "RTX 3060 Laptop 6GB · Ollama 0.40.16"

    record = model_client.record(call, "passed")
    lines = store.read_jsonl("usage/model_calls.jsonl")
    assert len(lines) == 1 and ModelCallRecord.model_validate(lines[0]) == record
    assert lines[0]["total_tokens"] == 150 and lines[0]["tokens_source"] == "runtime"
    assert lines[0]["response_id"] == "resp_x" and lines[0]["reused"] is False and lines[0]["provider"] == "ollama"


def test_think_not_sent_without_capability(ollama):
    ollama.capabilities = ["completion"]
    asyncio.run(ask())
    assert "think" not in ollama.chats[-1]


def test_calls_are_serialized(ollama):
    async def go():
        return await asyncio.gather(*(ask() for _ in range(4)))

    calls = asyncio.run(go())
    assert ollama.max_active == 1 and any(c.wait_ms > 0 for c in calls)


def test_startup_warms_model_and_health_reports_it(ollama, monkeypatch):
    monkeypatch.setenv("TPT__OLLAMA__WARMUP", "true")
    get_config.cache_clear()
    with TestClient(app) as client:
        for _ in range(100):
            if model_client.status().warm:
                break
            time.sleep(0.01)
        model = client.get("/api/v1/health").json()["model"]
    assert isinstance(model.pop("load_ms"), int)  # wall time of the warm-up call
    assert model == {
        "reachable": True,
        "model": MODEL,
        "warm": True,
        "version": "0.40.16",
        "error": None,
    }
    assert ollama.chats[0]["messages"] == [] and ollama.chats[0]["keep_alive"] == "30m"


def test_unreachable_is_reported_with_linux_fix(caplog):
    status = asyncio.run(model_client.startup())  # conftest transport refuses connections
    assert status.reachable is False and status.warm is False and "cannot reach Ollama" in status.error
    assert "OLLAMA_HOST=172.17.0.1:11434" in caplog.text
    with pytest.raises(model_client.ModelUnavailableError):
        asyncio.run(ask())


def test_cloud_disabled_or_keyless_is_refused(monkeypatch):
    monkeypatch.setenv("TPT__MODELS__ASSISTANT__PROVIDER", '"cloud"')
    get_config.cache_clear()
    with pytest.raises(model_client.ModelUnavailableError, match="disabled"):
        asyncio.run(ask())
    monkeypatch.setenv("CLOUD_ENABLED", "true")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    get_config.cache_clear()
    with pytest.raises(model_client.ModelUnavailableError, match="API key"):
        asyncio.run(ask())


def test_cloud_call_when_enabled(monkeypatch):
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["auth"] = request.headers["authorization"]
        sent["body"] = json.loads(request.content)
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"x"}'}}], "usage": usage})

    monkeypatch.setattr(model_client, "cloud_transport", httpx.MockTransport(handler))
    monkeypatch.setenv("TPT__MODELS__ASSISTANT__PROVIDER", '"cloud"')
    monkeypatch.setenv("CLOUD_ENABLED", "true")
    monkeypatch.setenv("TPT__CLOUD__MODEL", '"llama-3.1-8b-instant"')
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    get_config.cache_clear()
    call = asyncio.run(ask())
    assert call.provider == "cloud" and call.prompt_tokens == 10 and sent["auth"] == "Bearer test-key"
    assert sent["body"]["response_format"]["json_schema"]["schema"] == Answer.model_json_schema()
    assert model_client.record(call, "passed").provider == "cloud"


def test_only_model_client_calls_the_runtime():
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        str(p)
        for p in app_dir.rglob("*.py")
        if p.name != "model_client.py" and ("import ollama" in (text := p.read_text()) or "/api/chat" in text)
    ]
    assert offenders == []


@pytest.mark.ollama
@pytest.mark.skipif(os.environ.get("RUN_OLLAMA_TESTS") != "1", reason="set RUN_OLLAMA_TESTS=1 for live Ollama")
def test_live_ollama_call_and_record():
    get_config.cache_clear()

    class Summary(BaseModel):
        field_count: int
        submit_label: str

    async def go():
        status = await model_client.startup()
        assert status.reachable and status.warm, status
        return await model_client.call(
            "assistant",
            [
                {"role": "system", "content": "Answer with JSON only."},
                {
                    "role": "user",
                    "content": "A login form has an Email input, a Password input and a 'Sign in' "
                    "button. How many input fields are there, and what is the button label?",
                },
            ],
            Summary.model_json_schema(),
            session_id="ses_live",
            feature="live_test",
        )

    call = asyncio.run(go())
    answer = Summary.model_validate_json(call.content)
    record = model_client.record(call, "passed")
    print("\nLIVE", record.model_dump_json(), "answer:", answer.model_dump())
    assert record.prompt_tokens and record.completion_tokens and record.response_ms
    assert answer.field_count == 2
