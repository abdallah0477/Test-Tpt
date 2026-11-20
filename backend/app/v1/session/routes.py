"""Sessions: create, read, list their Inspections, close the Runner context.

v1/session is the only writer of sessions/{ses}/session.json (store.update_json).
The list of Inspections is derived by scanning inspections/*/inspection.json
(written by v1/inspection), so v1/inspection never writes session.json (AD-1, AD-4).

Every write recomputes `confidence` and `actionable` with utils/confidence (AD-16).

Clarification ownership split: v1/assistant only GENERATES a question (a validated
AssistantResponse in mode "clarification", written by utils/agent_loop). v1/session
PERSISTS it as a ClarificationTurn by reading that stored response
(POST /{id}/clarification {response_id}), and records answers and skips. So
session.json keeps one writer, and the question text always comes from a
validated, stored response, never from the client.
"""

import logging
from collections.abc import Callable

from contracts import (
    AssistantResponse,
    ClarificationTurn,
    FindingRef,
    GoalEntry,
    Scope,
    ScopeFilters,
    Session,
    is_id,
    new_id,
    utc_now,
)
from fastapi import APIRouter, Header, Response

from app.utils import confidence, context, runner_client, store
from app.utils.errors import ApiError
from app.utils.scope_filter import apply_filters
from app.v1.session.schemas import (
    AnswerRequest,
    ClarificationFromResponse,
    FilterPreview,
    FilterPreviewRequest,
    GoalRequest,
    InspectionSummary,
    ScopeRequest,
)

log = logging.getLogger("app.session")

router = APIRouter(prefix="/api/v1/session", tags=["session"])


_path = context.session_path
_session_inspections = context.session_inspections
_load = context.load_session
_session_inspection = context.session_inspection
_context_inspection = context.context_inspection


def _parse_if_match(if_match: str | None) -> int:
    """`If-Match: <rev>` (quotes and W/ allowed). Required on every session write (AD-14)."""
    if if_match is None:
        raise ApiError(428, "if_match_required", "send If-Match: <rev> from the last Session you read")
    raw = if_match.strip().removeprefix("W/").strip('"')
    if not raw.isdigit():
        raise ApiError(400, "invalid_if_match", "If-Match must be the Session rev, e.g. If-Match: 3")
    return int(raw)


def _update(session_id: str, if_match: str | None, change: Callable[[Session], None], response: Response) -> Session:
    """Read-modify-write session.json with optimistic concurrency; stale rev -> 409 rev_conflict."""
    expected = _parse_if_match(if_match)
    _load(session_id)

    def apply(current: dict) -> dict:
        session = Session.model_validate(current)
        change(session)
        report = confidence.compute(session, _context_inspection(session))
        session.confidence = report.score
        session.actionable = report.actionable
        session.updated_at = utc_now()
        return session.model_dump(mode="json")

    store.update_json(_path(session_id), apply, expected_rev=expected)
    session = _load(session_id)
    response.headers["ETag"] = str(session.rev)
    return session


@router.post("", response_model=Session, status_code=201)
def create_session(response: Response) -> Session:
    session = Session(session_id=new_id("ses"))
    stored = store.update_json(_path(session.session_id), lambda _: session.model_dump(mode="json"), expected_rev=0)
    response.headers["ETag"] = str(stored["rev"])
    log.info("session created", extra={"session_id": session.session_id})
    return Session.model_validate(stored)


@router.get("/{session_id}", response_model=Session)
def get_session(session_id: str, response: Response) -> Session:
    session = _load(session_id)
    response.headers["ETag"] = str(session.rev)
    return session


@router.get("/{session_id}/inspections", response_model=list[InspectionSummary])
def list_inspections(session_id: str) -> list[InspectionSummary]:
    _load(session_id)
    return [
        InspectionSummary(
            inspection_id=i.inspection_id,
            requested_url=i.requested_url,
            captured_at=i.captured_at,
            status=i.status,
            counts=i.counts,
        )
        for i in _session_inspections(session_id)
    ]


@router.post("/{session_id}/close", status_code=204)
async def close_session(session_id: str) -> Response:
    """Close the Session's long-lived inspection context in the Runner."""
    _load(session_id)
    try:
        await runner_client.close(session_id)
    except runner_client.RunnerError as exc:
        raise ApiError(503, "runner_unavailable", "the Runner could not close the inspection context") from exc
    return Response(status_code=204)


@router.put("/{session_id}/goal", response_model=Session)
def set_goal(
    session_id: str, body: GoalRequest, response: Response, if_match: str | None = Header(default=None)
) -> Session:
    """Append a Testing goal; the last one is current, earlier ones stay as history. Scope is untouched."""
    text = body.text.strip()
    if not text:
        raise ApiError(422, "invalid_goal", "the goal must not be empty")

    def change(session: Session) -> None:
        if session.current_goal != text:
            session.goals.append(GoalEntry(text=text))

    return _update(session_id, if_match, change, response)


@router.put("/{session_id}/scope", response_model=Session)
def set_scope(
    session_id: str, body: ScopeRequest, response: Response, if_match: str | None = Header(default=None)
) -> Session:
    """Replace the Scope: refs of one stored Inspection of this Session (duplicates are dropped)."""
    inspection = _session_inspection(session_id, body.inspection_id)
    known = {f.finding_id for f in inspection.findings}
    errors = []
    refs: list[FindingRef] = []
    for ref in body.refs:
        if ref.inspection_id != body.inspection_id:
            errors.append(f"{ref.inspection_id}/{ref.finding_id} belongs to another inspection")
        elif ref.finding_id not in known:
            errors.append(f"{ref.finding_id} is not a Finding of {body.inspection_id}")
        elif ref not in refs:
            refs.append(ref)
    if errors:
        raise ApiError(422, "invalid_scope", "the Scope names Findings that were not recorded", {"errors": errors})

    def change(session: Session) -> None:
        session.scope = Scope(inspection_id=body.inspection_id, refs=refs)

    return _update(session_id, if_match, change, response)


@router.put("/{session_id}/filters", response_model=Session)
def set_filters(
    session_id: str, body: ScopeFilters, response: Response, if_match: str | None = Header(default=None)
) -> Session:
    """Store the active group filters. Applying them to the Scope is a separate PUT /scope."""

    def change(session: Session) -> None:
        session.filters = body

    return _update(session_id, if_match, change, response)


@router.post("/{session_id}/filter-preview", response_model=FilterPreview)
def filter_preview(session_id: str, body: FilterPreviewRequest) -> FilterPreview:
    """Findings of a stored Inspection that match the filters (AND logic, see utils/scope_filter). Stores nothing."""
    _load(session_id)
    inspection = _session_inspection(session_id, body.inspection_id)
    ids = [f.finding_id for f in apply_filters(inspection.findings, body.filters)]
    return FilterPreview(inspection_id=body.inspection_id, finding_ids=ids, count=len(ids))


@router.get("/{session_id}/confidence", response_model=confidence.ConfidenceReport)
def get_confidence(session_id: str) -> confidence.ConfidenceReport:
    """The current confidence with its signals (computed, never from the model)."""
    session = _load(session_id)
    return confidence.compute(session, _context_inspection(session))


@router.post("/{session_id}/clarification", response_model=Session)
def add_clarification(
    session_id: str, body: ClarificationFromResponse, response: Response, if_match: str | None = Header(default=None)
) -> Session:
    """Store the question of a validated clarification response as a new turn (clr_ id)."""
    path = f"sessions/{session_id}/responses/{body.response_id}.json"
    if not is_id(body.response_id, "resp") or not is_id(session_id, "ses") or not store.exists(path):
        raise ApiError(404, "response_not_found", f"response {body.response_id} is not stored in this session")
    stored = AssistantResponse.model_validate(store.read_json(path))
    if stored.mode != "clarification" or not stored.sections.next_step:
        raise ApiError(422, "no_question", "this response holds no validated clarification question")
    question = stored.sections.next_step[0]
    asked = confidence.normalize_question(question.text)

    def change(session: Session) -> None:
        if any(confidence.normalize_question(t.question) == asked for t in session.clarification):
            raise ApiError(409, "duplicate_question", "this question was already asked in the session")
        session.clarification.append(
            ClarificationTurn(clr_id=new_id("clr"), question=question.text, refs=question.refs)
        )

    return _update(session_id, if_match, change, response)


def _close_turn(session: Session, clr_id: str) -> ClarificationTurn:
    turn = next((t for t in session.clarification if t.clr_id == clr_id), None)
    if turn is None:
        raise ApiError(404, "clarification_not_found", f"no clarification turn {clr_id}")
    if turn.answer is not None or turn.skipped:
        raise ApiError(409, "clarification_closed", "this question was already answered or skipped")
    turn.answered_at = utc_now()
    return turn


@router.post("/{session_id}/clarification/{clr_id}/answer", response_model=Session)
def answer_clarification(
    session_id: str, clr_id: str, body: AnswerRequest, response: Response, if_match: str | None = Header(default=None)
) -> Session:
    text = body.text.strip()
    if not text:
        raise ApiError(422, "invalid_answer", "the answer must not be empty")

    def change(session: Session) -> None:
        _close_turn(session, clr_id).answer = text

    return _update(session_id, if_match, change, response)


@router.post("/{session_id}/clarification/{clr_id}/skip", response_model=Session)
def skip_clarification(
    session_id: str, clr_id: str, response: Response, if_match: str | None = Header(default=None)
) -> Session:
    """Explicit skip only (never on a timeout); the assistant then offers suggestions."""

    def change(session: Session) -> None:
        _close_turn(session, clr_id).skipped = True

    return _update(session_id, if_match, change, response)
