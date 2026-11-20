"""Backend <-> Runner job API (AD-19).

The backend allocates every id and passes it as ``job_id`` (the ``ins_`` id for
inspections). The Runner writes the result to the exchange volume at
``out/{job_id}/result.json`` (an :class:`InspectionResult`), puts binary files
next to it (``screenshot.png``, ``crops/{finding_id}.png``) and writes the
``DONE`` marker last. Paths inside the result are relative to ``out/{job_id}/``;
the backend rewrites them relative to ``data/`` when it imports.
"""

from pydantic import Field

from contracts.models import Inspection, Model


class InspectRequest(Model):
    """POST /inspect and POST /reinspect body."""

    job_id: str = Field(description="Backend-allocated ins_ id; also the out/ folder name")
    session_id: str = Field(description="Selects the Session's long-lived inspection context (AD-20)")
    url: str
    allowed_origins: list[str] = Field(description="From gates.approved_origins(); others are aborted")
    load_timeout_ms: int = Field(default=30000, ge=1000)


class CloseRequest(Model):
    """POST /close body: closes the Session's inspection context."""

    session_id: str


class JobAccepted(Model):
    """Response of POST /inspect and /reinspect."""

    job_id: str
    queue_position: int = Field(ge=0)


class InspectionResult(Model):
    """Contents of out/{job_id}/result.json for an inspection job."""

    inspection: Inspection
    login_detected: bool = Field(default=False, description="Heuristic: password field / login redirect seen")
