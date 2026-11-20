"""Usage: the Session's ModelCallRecords, grouped per response for the usage badge (Story 3.5, AD-9, AD-18).

Reads usage/model_calls.jsonl through store only (written by utils/model_client).
Badge totals count only records with reused == false; reused records are listed
and counted separately. Model time is never mixed with browser time.
"""

from contracts import ModelCallRecord, is_id
from contracts.models import Model
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.utils import context, store
from app.utils.errors import ApiError

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])

USAGE_PATH = "usage/model_calls.jsonl"


class ResponseUsage(Model):
    """Badge data: "model · N calls · T tokens · S s" (fresh calls only)."""

    response_id: str | None
    model: str
    calls: int
    reused_calls: int
    total_tokens: int
    response_ms: int
    load_ms: int
    outcome: str = ""
    call_ids: list[str]


class SessionUsage(Model):
    session_id: str
    records: list[ModelCallRecord]
    responses: list[ResponseUsage]
    total_calls: int
    total_tokens: int
    total_response_ms: int


def _records(session_id: str) -> list[ModelCallRecord]:
    if not is_id(session_id, "ses"):
        raise ApiError(404, "session_not_found", f"session {session_id} does not exist")
    context.load_session(session_id)
    rows = [ModelCallRecord.model_validate(r) for r in store.read_jsonl(USAGE_PATH)]
    return [r for r in rows if r.session_id == session_id]


def _group(records: list[ModelCallRecord]) -> list[ResponseUsage]:
    groups: dict[str | None, list[ModelCallRecord]] = {}
    for record in records:
        groups.setdefault(record.response_id, []).append(record)
    out = []
    for response_id, rows in groups.items():
        fresh = [r for r in rows if not r.reused]
        out.append(
            ResponseUsage(
                response_id=response_id,
                model=rows[-1].model,
                calls=len(fresh),
                reused_calls=len(rows) - len(fresh),
                total_tokens=sum(r.total_tokens or 0 for r in fresh),
                response_ms=sum(r.response_ms or 0 for r in fresh),
                load_ms=sum(r.load_ms or 0 for r in fresh),
                outcome=rows[-1].validation_outcome.value,
                call_ids=[r.call_id for r in rows],
            )
        )
    return out


@router.get("/{session_id}", response_model=SessionUsage)
def session_usage(session_id: str) -> SessionUsage:
    records = _records(session_id)
    fresh = [r for r in records if not r.reused]
    return SessionUsage(
        session_id=session_id,
        records=records,
        responses=_group(records),
        total_calls=len(fresh),
        total_tokens=sum(r.total_tokens or 0 for r in fresh),
        total_response_ms=sum(r.response_ms or 0 for r in fresh),
    )


@router.get("/{session_id}/export", response_model=list[ModelCallRecord])
def export_usage(session_id: str) -> JSONResponse:
    """Every ModelCallRecord field for the Session, as a JSON file readable without the app."""
    records = _records(session_id)
    return JSONResponse(
        content=[r.model_dump(mode="json") for r in records],
        headers={"Content-Disposition": f'attachment; filename="model_calls_{session_id}.json"'},
    )
