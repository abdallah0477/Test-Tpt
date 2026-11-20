"""The only code that calls a model runtime (AD-2, AD-7, AD-8, AD-9).

    await call(role, messages, schema, session_id=..., feature=..., ...) -> ModelCall
    record(call, validation_outcome, reused=False)                      -> ModelCallRecord
    await startup()   health check + warm-up (never raises; see status())
    status()          {reachable, model, warm, version, error} for /api/v1/health

Ollama: POST /api/chat with `format` = the JSON schema, stream=false, keep_alive,
options {num_ctx, temperature, num_predict}. `think` is sent only when /api/show
lists the "thinking" capability, and then with the role's configured value
(false by default). Calls are serialized (one at a time, AD-9).

Cloud (Groq, OpenAI-compatible) is used only when config cloud.enabled is true
and GROQ_API_KEY is set; otherwise calls to it are refused. Its calls are throttled
to cloud.rpm_limit / cloud.tpm_limit and recorded with provider "cloud".
"""

import asyncio
import logging
import os
import time
import weakref
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import httpx
from contracts import ModelCallRecord, ValidationOutcome, new_id, utc_now
from contracts.models import Model
from pydantic import Field

from app.utils import store
from app.utils.config import ModelRole, get_config

log = logging.getLogger("app.model_client")

USAGE_PATH = "usage/model_calls.jsonl"
LINUX_FIX = (
    "Ollama is not reachable. On Linux, make Ollama listen on the Docker bridge: "
    "`sudo systemctl edit ollama` -> [Service] Environment=OLLAMA_HOST=172.17.0.1:11434, "
    "then `sudo systemctl restart ollama` (never 0.0.0.0)."
)

# Tests replace these with httpx.MockTransport fakes.
transport: httpx.AsyncBaseTransport | None = None
cloud_transport: httpx.AsyncBaseTransport | None = None


class ModelError(Exception):
    """The model runtime failed or returned something unusable."""


class ModelUnavailableError(ModelError):
    """No runtime can serve the call (Ollama down, cloud disabled or without a key)."""


@dataclass
class ModelCall:
    """One attempt, measured. `content` is the raw JSON text the model returned."""

    call_id: str
    session_id: str
    feature: str
    role: Literal["assistant", "codegen"]
    provider: Literal["ollama", "cloud"]
    model: str
    setup: str
    content: str
    started_at: datetime
    inspection_id: str | None = None
    response_id: str | None = None
    attempt: int = 1
    prompt_tokens: int | None = None  # Ollama prompt_eval_count
    completion_tokens: int | None = None  # Ollama eval_count
    load_ms: int | None = None  # Ollama load_duration
    wait_ms: int = 0  # time spent waiting for the serialization lock
    response_ms: int | None = None  # total_duration minus load_duration
    total_ms: int | None = None  # Ollama total_duration (wall time if missing)
    eval_ms: int | None = None  # Ollama eval_duration: generation only (tokens/s = completion_tokens / eval_ms)
    tokens_source: Literal["runtime", "estimate"] = "runtime"


class ModelStatus(Model):
    reachable: bool = False
    model: str = ""
    warm: bool = False
    version: str | None = None
    error: str | None = None
    load_ms: int | None = Field(default=None, description="Model load time measured by the warm-up call")


@dataclass
class _State:
    status: ModelStatus = field(default_factory=ModelStatus)
    capabilities: dict[str, list[str]] = field(default_factory=dict)
    cloud_calls: deque = field(default_factory=deque)  # (monotonic time, tokens)


_state = _State()
_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()


def _lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    if loop not in _locks:
        _locks[loop] = asyncio.Lock()
    return _locks[loop]


def _role(role: str) -> ModelRole:
    roles = get_config().models
    if role not in ("assistant", "codegen"):
        raise ValueError(f"unknown model role: {role!r}")
    return getattr(roles, role)


def _client(timeout: float | None = None) -> httpx.AsyncClient:
    config = get_config().ollama
    seconds = timeout if timeout is not None else config.request_timeout_ms / 1000
    return httpx.AsyncClient(base_url=config.base_url, transport=transport, timeout=seconds)


def _ms(ns: Any) -> int | None:
    return int(ns) // 1_000_000 if isinstance(ns, int | float) else None


def setup_string(provider: str = "ollama") -> str:
    if provider == "cloud":
        return f"{get_config().cloud.provider} API (cloud)"
    hardware = get_config().ollama.hardware.strip()
    version = _state.status.version
    runtime = f"Ollama {version}" if version else "Ollama"
    return f"{hardware} · {runtime}" if hardware else runtime


async def unload_all() -> list[str]:
    """Unload every model Ollama has in memory (keep_alive 0); for cold-load measurements."""
    async with _client(timeout=60.0) as client:
        running = (await client.get("/api/ps")).json().get("models") or []
        for model in running:
            await client.post("/api/generate", json={"model": model["name"], "keep_alive": 0})
        for _ in range(60):  # unloading finishes asynchronously
            if not (await client.get("/api/ps")).json().get("models"):
                break
            await asyncio.sleep(0.5)
    _state.status.warm = False
    return [m["name"] for m in running]


def status() -> ModelStatus:
    current = _state.status.model_copy()
    current.model = current.model or get_config().models.assistant.model
    return current


def reset() -> None:
    """Forget health, capabilities and cloud throttle state (tests)."""
    global _state
    _state = _State()


# ---------------------------------------------------------------- health and warm-up


async def _capabilities(client: httpx.AsyncClient, model: str) -> list[str]:
    if model not in _state.capabilities:
        response = await client.post("/api/show", json={"model": model})
        response.raise_for_status()
        _state.capabilities[model] = list(response.json().get("capabilities") or [])
    return _state.capabilities[model]


async def startup() -> ModelStatus:
    """Health-check Ollama, then load the assistant model with keep_alive. Never raises."""
    config = get_config()
    role = config.models.assistant
    _state.status = ModelStatus(model=role.model)
    if role.provider != "ollama":
        return status()
    try:
        async with _client(timeout=10.0) as client:
            version = await client.get("/api/version")
            version.raise_for_status()
            _state.status.reachable = True
            _state.status.version = version.json().get("version")
            await _capabilities(client, role.model)
        async with _lock(), _client() as client:
            began = time.monotonic()
            # an empty chat loads the model into memory without generating anything
            warm = await client.post(
                "/api/chat",
                # same num_ctx as real calls, or Ollama reloads the model on the first call
                json={
                    "model": role.model,
                    "messages": [],
                    "keep_alive": config.ollama.keep_alive,
                    "options": {"num_ctx": role.num_ctx},
                },
            )
            warm.raise_for_status()
        _state.status.warm = True
        # an empty chat reports no load_duration; its wall time is the load time
        _state.status.load_ms = _ms(warm.json().get("load_duration")) or int((time.monotonic() - began) * 1000)
        log.info("model warm", extra={"path": role.model})
    except httpx.HTTPStatusError as exc:
        _state.status.error = f"Ollama answered HTTP {exc.response.status_code} for {role.model}"
        log.error(_state.status.error)
    except httpx.TransportError as exc:
        _state.status.error = f"cannot reach Ollama at {config.ollama.base_url}: {type(exc).__name__}"
        log.error(f"{_state.status.error}. {LINUX_FIX}")
    except Exception as exc:  # noqa: BLE001 - startup must never fail on the model
        _state.status.error = f"model warm-up failed: {type(exc).__name__}"
        log.error(_state.status.error, exc_info=exc)
    return status()


# ---------------------------------------------------------------- calls


async def call(
    role: Literal["assistant", "codegen"],
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    session_id: str,
    feature: str,
    inspection_id: str | None = None,
    response_id: str | None = None,
    attempt: int = 1,
) -> ModelCall:
    """One schema-constrained chat call, measured. Raises ModelUnavailableError / ModelError."""
    settings = _role(role)
    context = {
        "call_id": new_id("call"),
        "session_id": session_id,
        "feature": feature,
        "role": role,
        "inspection_id": inspection_id,
        "response_id": response_id,
        "attempt": attempt,
    }
    queued = time.monotonic()
    async with _lock():
        wait_ms = int((time.monotonic() - queued) * 1000)
        if settings.provider == "cloud":
            return await _call_cloud(settings, messages, schema, context, wait_ms)
        try:
            return await _call_ollama(settings, messages, schema, context, wait_ms)
        except ModelUnavailableError:
            if not _cloud_ready():
                raise
            log.warning("Ollama unavailable; using the enabled cloud fallback")
            return await _call_cloud(settings, messages, schema, context, wait_ms)


async def _call_ollama(
    settings: ModelRole, messages: list[dict], schema: dict, context: dict, wait_ms: int
) -> ModelCall:
    config = get_config().ollama
    body: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "format": schema,
        "stream": False,
        "keep_alive": config.keep_alive,
        "options": {
            "num_ctx": settings.num_ctx,
            "temperature": settings.temperature,
            "num_predict": settings.num_predict,
        },
    }
    started_at = utc_now()
    began = time.monotonic()
    try:
        async with _client() as client:
            if "thinking" in await _capabilities(client, settings.model):
                body["think"] = settings.think
            response = await client.post("/api/chat", json=body)
    except httpx.TransportError as exc:
        _state.status.reachable = False
        _state.status.warm = False
        log.error(f"cannot reach Ollama at {config.base_url}. {LINUX_FIX}")
        raise ModelUnavailableError(f"cannot reach Ollama at {config.base_url}") from exc
    except httpx.HTTPStatusError as exc:  # from /api/show
        raise ModelError(f"Ollama /api/show answered HTTP {exc.response.status_code}") from exc
    wall_ms = int((time.monotonic() - began) * 1000)
    if response.status_code >= 400:
        raise ModelError(f"Ollama /api/chat answered HTTP {response.status_code}")
    try:
        data = response.json()
        content = data["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ModelError("Ollama returned an unexpected body") from exc
    _state.status.reachable = True
    _state.status.warm = True
    load_ms = _ms(data.get("load_duration"))
    total_ms = _ms(data.get("total_duration")) or wall_ms
    return ModelCall(
        **context,
        provider="ollama",
        model=settings.model,
        setup=setup_string("ollama"),
        content=content,
        started_at=started_at,
        prompt_tokens=data.get("prompt_eval_count"),
        completion_tokens=data.get("eval_count"),
        load_ms=load_ms,
        wait_ms=wait_ms,
        response_ms=total_ms - (load_ms or 0),
        total_ms=total_ms,
        eval_ms=_ms(data.get("eval_duration")),
        tokens_source="runtime",
    )


def _cloud_key() -> str | None:
    provider = get_config().cloud.provider
    return os.environ.get("GROQ_API_KEY") if provider == "groq" else None


def _cloud_ready() -> bool:
    config = get_config().cloud
    return config.enabled and bool(config.model) and bool(_cloud_key())


async def _throttle(estimated_tokens: int) -> None:
    """Wait until another call fits the cloud RPM / TPM limits (sliding 60 s window)."""
    config = get_config().cloud
    while True:
        now = time.monotonic()
        while _state.cloud_calls and now - _state.cloud_calls[0][0] > 60:
            _state.cloud_calls.popleft()
        tokens = sum(t for _, t in _state.cloud_calls)
        if len(_state.cloud_calls) < config.rpm_limit and tokens + estimated_tokens <= config.tpm_limit:
            return
        if not _state.cloud_calls:
            return  # a single call larger than the TPM limit; let the provider decide
        await asyncio.sleep(max(0.1, 60 - (now - _state.cloud_calls[0][0])))


async def _call_cloud(
    settings: ModelRole, messages: list[dict], schema: dict, context: dict, wait_ms: int
) -> ModelCall:
    config = get_config().cloud
    if not config.enabled:
        raise ModelUnavailableError("the cloud provider is disabled (config cloud.enabled = false)")
    key = _cloud_key()
    if not key or not config.model:
        raise ModelUnavailableError(f"the cloud provider {config.provider} needs an API key in .env and cloud.model")
    estimate = sum(len(m.get("content", "")) for m in messages) // 3 + settings.num_predict
    await _throttle(estimate)
    body = {
        "model": config.model,
        "messages": messages,
        "temperature": settings.temperature,
        "max_tokens": settings.num_predict,
        "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
    }
    started_at = utc_now()
    began = time.monotonic()
    try:
        async with httpx.AsyncClient(base_url=config.base_url, transport=cloud_transport, timeout=120) as client:
            response = await client.post("/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"})
    except httpx.TransportError as exc:
        raise ModelUnavailableError(f"cannot reach the cloud provider {config.provider}") from exc
    elapsed = int((time.monotonic() - began) * 1000)
    if response.status_code >= 400:
        raise ModelError(f"cloud provider answered HTTP {response.status_code}")
    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ModelError("cloud provider returned an unexpected body") from exc
    usage = data.get("usage") or {}
    _state.cloud_calls.append((time.monotonic(), int(usage.get("total_tokens") or estimate)))
    return ModelCall(
        **context,
        provider="cloud",
        model=config.model,
        setup=setup_string("cloud"),
        content=content,
        started_at=started_at,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        load_ms=None,
        wait_ms=wait_ms,
        response_ms=elapsed,
        total_ms=elapsed,
        tokens_source="runtime" if usage else "estimate",
    )


# ---------------------------------------------------------------- usage records


def record(call: ModelCall, validation_outcome: ValidationOutcome | str, *, reused: bool = False) -> ModelCallRecord:
    """Append one ModelCallRecord for this attempt, after validation (AD-9)."""
    total = None
    if call.prompt_tokens is not None or call.completion_tokens is not None:
        total = (call.prompt_tokens or 0) + (call.completion_tokens or 0)
    entry = ModelCallRecord(
        call_id=new_id("call") if reused else call.call_id,
        session_id=call.session_id,
        inspection_id=call.inspection_id,
        feature=call.feature,
        response_id=call.response_id,
        attempt=call.attempt,
        role=call.role,
        provider=call.provider,
        model=call.model,
        setup=call.setup,
        prompt_tokens=call.prompt_tokens,
        completion_tokens=call.completion_tokens,
        total_tokens=total,
        tokens_source=call.tokens_source,
        load_ms=call.load_ms,
        wait_ms=call.wait_ms,
        response_ms=call.response_ms,
        started_at=utc_now() if reused else call.started_at,
        validation_outcome=ValidationOutcome(validation_outcome),
        reused=reused,
    )
    store.append_jsonl(USAGE_PATH, entry)
    return entry
