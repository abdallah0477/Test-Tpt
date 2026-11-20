"""Assistant: Scope summary (3.3), clarification questions (3.4), suggestions.

Every answer goes through utils/agent_loop (validate -> retry -> block) and is
stored by it as an AssistantResponse. v1/assistant never writes session.json:
a clarification question becomes a Session turn only when the client calls
POST /api/v1/session/{id}/clarification {response_id} (owned by v1/session).

Flow: POST summary | clarify | suggestions -> {job_id} -> SSE /events/{job_id}
-> job_done.data.result_id -> GET /responses/{response_id}?session_id=...
"""

from contracts import AssistantResponse, Session, SseEvent, is_id
from fastapi import APIRouter, Query

from app.utils import agent_loop, confidence, context, model_client, store
from app.utils.agent_loop import AnswerSections, LoopScope
from app.utils.errors import ApiError
from app.utils.events import event_response
from app.v1.assistant import jobs, prompts
from app.v1.assistant.schemas import AssistantJob, AssistantRequest, ClarificationOutput, SuggestionsRequest

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

FEATURE = "assistant"
_SSE = {200: {"description": "SSE stream of SseEvent", "content": {"text/event-stream": {}}}}


async def _require_model() -> None:
    """503 when the model runtime is known to be down (re-probed once)."""
    status = model_client.status()
    if status.reachable or status.error is None:
        return
    status = await model_client.startup()
    if not status.reachable:
        raise ApiError(503, "model_unavailable", status.error or "the model runtime is not reachable")


def _context(session_id: str):
    session = context.load_session(session_id)
    inspection = context.context_inspection(session)
    if inspection is None:
        raise ApiError(409, "no_inspection", "inspect a page first")
    return session, inspection, confidence.compute(session, inspection)


def _skipped_last(session: Session) -> bool:
    return bool(session.clarification) and session.clarification[-1].skipped


def _start_clarification(session, inspection, report) -> jobs.Job:
    scope = LoopScope(inspection)  # questions may point at any observed Finding

    async def runner(job: jobs.Job) -> agent_loop.LoopResult:
        return await agent_loop.run(
            FEATURE,
            ClarificationOutput,
            prompts.clarification_parts(session, inspection.findings, inspection, report),
            scope,
            session_id=session.session_id,
            mode="clarification",
            check=prompts.clarification_check(session, report),
            preface=prompts.absence_preface(report),
            response_id=job.job_id,
            progress=job.progress,
        )

    return jobs.start(session.session_id, runner)


def _scoped(session, inspection) -> LoopScope:
    if not session.scope.refs or session.scope.inspection_id != inspection.inspection_id:
        raise ApiError(409, "scope_empty", "select Findings into the Scope first")
    return LoopScope(inspection, refs=list(session.scope.refs))


@router.post("/summary", response_model=AssistantJob, status_code=202)
async def summary(body: AssistantRequest) -> AssistantJob:
    """Summarise the Scope; if the goal isn't actionable (and the last question wasn't skipped), clarify first."""
    session, inspection, report = _context(body.session_id)
    scope = _scoped(session, inspection)
    await _require_model()
    if not report.actionable and not _skipped_last(session):
        job = _start_clarification(session, inspection, report)
        return AssistantJob(job_id=job.job_id, kind="clarification", needs_clarification=True, confidence=report.score)

    async def runner(job: jobs.Job) -> agent_loop.LoopResult:
        return await agent_loop.run(
            FEATURE,
            AnswerSections,
            prompts.summary_parts(session, list(scope.in_scope().values()), inspection),
            scope,
            session_id=session.session_id,
            mode="summary",
            response_id=job.job_id,
            progress=job.progress,
        )

    job = jobs.start(session.session_id, runner)
    return AssistantJob(job_id=job.job_id, kind="summary", confidence=report.score)


@router.post("/clarify", response_model=AssistantJob, status_code=202)
async def clarify(body: AssistantRequest) -> AssistantJob:
    """Generate the next clarification question (store it with POST /api/v1/session/{id}/clarification)."""
    session, inspection, report = _context(body.session_id)
    await _require_model()
    job = _start_clarification(session, inspection, report)
    return AssistantJob(job_id=job.job_id, kind="clarification", confidence=report.score)


@router.post("/suggestions", response_model=AssistantJob, status_code=202)
async def suggestions(body: SuggestionsRequest) -> AssistantJob:
    """Testing suggestions (mode "suggestions") for one Finding, or for the Scope after a skip."""
    session, inspection, report = _context(body.session_id)
    if body.finding_ref is not None:
        inspection = context.session_inspection(session.session_id, body.finding_ref.inspection_id)
        if body.finding_ref.finding_id not in {f.finding_id for f in inspection.findings}:
            raise ApiError(404, "finding_not_found", f"{body.finding_ref.finding_id} is not a recorded Finding")
        scope = LoopScope(inspection, refs=[body.finding_ref])
    else:
        scope = _scoped(session, inspection)
    await _require_model()

    async def runner(job: jobs.Job) -> agent_loop.LoopResult:
        return await agent_loop.run(
            FEATURE,
            AnswerSections,
            prompts.suggestion_parts(session, list(scope.in_scope().values()), inspection),
            scope,
            session_id=session.session_id,
            mode="suggestions",
            response_id=job.job_id,
            progress=job.progress,
        )

    job = jobs.start(session.session_id, runner)
    return AssistantJob(job_id=job.job_id, kind="suggestions", confidence=report.score)


@router.get("/events/{job_id}", response_model=SseEvent, responses=_SSE)
async def assistant_events(job_id: str):
    running = jobs.job(job_id) if is_id(job_id, "resp") else None
    if running is None:
        raise ApiError(404, "job_not_found", f"unknown assistant job {job_id}")
    return event_response(jobs.events(running))


@router.get("/responses/{response_id}", response_model=AssistantResponse)
def get_response(response_id: str, session_id: str = Query()) -> AssistantResponse:
    path = agent_loop.response_path(session_id, response_id)
    if not is_id(response_id, "resp") or not is_id(session_id, "ses") or not store.exists(path):
        raise ApiError(404, "response_not_found", f"response {response_id} is not stored in this session")
    return AssistantResponse.model_validate(store.read_json(path))
