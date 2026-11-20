"""FastAPI app: routes under /api/v1/<feature>, AD-14 error envelope, typed SSE schema.

Run (one worker): uv run uvicorn app.main:app --port 8000
"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any, Literal

from contracts import ErrorBody, ErrorEnvelope, sse_event_adapter
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils import model_client, store
from app.utils.config import get_config
from app.utils.errors import ApiError
from app.utils.gates import GateError
from app.utils.log import setup_logging
from app.v1.assistant import jobs as assistant_jobs
from app.v1.assistant.routes import router as assistant_router
from app.v1.inspection import jobs as inspection_jobs
from app.v1.inspection.routes import router as inspection_router
from app.v1.session.routes import router as session_router
from app.v1.usage.routes import router as usage_router

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config = get_config()
    setup_logging(config.logging.level)
    config.storage.data_dir.mkdir(parents=True, exist_ok=True)
    log.info("backend started", extra={"path": str(config.storage.data_dir)})
    inspection_jobs.recover()
    # health check + warm-up in the background: the app starts even if Ollama is down
    warmup = asyncio.create_task(model_client.startup()) if config.ollama.warmup else None
    yield
    if warmup is not None:
        warmup.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await warmup
    await inspection_jobs.shutdown()
    await assistant_jobs.shutdown()


app = FastAPI(title="Test-Tpt backend", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------- errors (AD-14)


def error_response(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {404: "not_found", 405: "method_not_allowed", 409: "conflict"}.get(exc.status_code, "http_error")
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]
    return error_response(422, "validation_error", "request is invalid", {"errors": errors})


@app.exception_handler(store.ConflictError)
async def conflict_error(_request: Request, exc: store.ConflictError) -> JSONResponse:
    details = {"expected_rev": exc.expected_rev, "current_rev": exc.current_rev}
    return error_response(409, "rev_conflict", "the resource changed; reload and retry", details)


@app.exception_handler(store.AlreadyExistsError)
async def exists_error(_request: Request, _exc: store.AlreadyExistsError) -> JSONResponse:
    return error_response(409, "already_exists", "the resource already exists")


@app.exception_handler(store.NotFoundError)
async def not_found_error(_request: Request, _exc: store.NotFoundError) -> JSONResponse:
    return error_response(404, "not_found", "the resource was not found")


@app.exception_handler(ApiError)
async def api_error(_request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status, exc.code, exc.message, exc.details)


@app.exception_handler(GateError)
async def gate_error(_request: Request, exc: GateError) -> JSONResponse:
    return error_response(403, "gate_not_satisfied", exc.message, {"action": exc.action})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled error", exc_info=exc, extra={"path": request.url.path, "method": request.method})
    return error_response(500, "internal_error", "unexpected server error")


# ---------------------------------------------------------------- routes

api = APIRouter(prefix="/api/v1")


class Health(BaseModel):
    status: Literal["ok"]
    model: model_client.ModelStatus


@api.get("/health", response_model=Health, tags=["health"])
def health() -> Health:
    """The backend is up; `model` reports Ollama reachability and warm-up of the assistant model."""
    return Health(status="ok", model=model_client.status())


app.include_router(api)
app.include_router(session_router)
app.include_router(inspection_router)
app.include_router(assistant_router)
app.include_router(usage_router)


# ---------------------------------------------------------------- OpenAPI


def openapi() -> dict:
    """Add the SSE event union and the error envelope to the schema, so
    openapi-typescript generates frontend types for them (AD-14)."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    ref = "#/components/schemas/{model}"
    for name, model_schema in (
        ("SseEvent", sse_event_adapter.json_schema(ref_template=ref)),
        ("ErrorEnvelope", ErrorEnvelope.model_json_schema(ref_template=ref)),
    ):
        components.update(model_schema.pop("$defs", {}))
        components[name] = model_schema
    app.openapi_schema = schema
    return schema


app.openapi = openapi
