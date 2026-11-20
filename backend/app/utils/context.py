"""Read-only access to stored Session context, shared by v1/session and v1/assistant (AD-1).

Only reads, through store. session.json is written only by v1/session and
inspection.json only by v1/inspection.
"""

from contracts import Inspection, Session, is_id

from app.utils import store
from app.utils.errors import ApiError


def session_path(session_id: str) -> str:
    return f"sessions/{session_id}/session.json"


def inspection_path(inspection_id: str) -> str:
    return f"inspections/{inspection_id}/inspection.json"


def session_inspections(session_id: str) -> list[Inspection]:
    """Stored Inspections of a Session, oldest first (ins_ ids are ULIDs)."""
    found = []
    for name in store.list_dir("inspections"):
        if is_id(name, "ins") and store.exists(inspection_path(name)):
            inspection = Inspection.model_validate(store.read_json(inspection_path(name)))
            if inspection.session_id == session_id:
                found.append(inspection)
    return sorted(found, key=lambda i: i.inspection_id)


def load_session(session_id: str) -> Session:
    """The stored Session with `inspection_ids` derived from the stored Inspections; 404 if missing."""
    if not is_id(session_id, "ses") or not store.exists(session_path(session_id)):
        raise ApiError(404, "session_not_found", f"session {session_id} does not exist")
    session = Session.model_validate(store.read_json(session_path(session_id)))
    session.inspection_ids = [i.inspection_id for i in session_inspections(session_id)]
    return session


def session_inspection(session_id: str, inspection_id: str) -> Inspection:
    """A stored Inspection that belongs to the Session (404 / 422 otherwise)."""
    if not is_id(inspection_id, "ins") or not store.exists(inspection_path(inspection_id)):
        raise ApiError(404, "inspection_not_found", f"inspection {inspection_id} is not stored")
    inspection = Inspection.model_validate(store.read_json(inspection_path(inspection_id)))
    if inspection.session_id != session_id:
        raise ApiError(422, "inspection_not_in_session", f"inspection {inspection_id} belongs to another session")
    return inspection


def context_inspection(session: Session) -> Inspection | None:
    """The Scope's Inspection, else the Session's latest one, else None."""
    if session.scope.inspection_id and store.exists(inspection_path(session.scope.inspection_id)):
        return Inspection.model_validate(store.read_json(inspection_path(session.scope.inspection_id)))
    inspections = session_inspections(session.session_id)
    return inspections[-1] if inspections else None
