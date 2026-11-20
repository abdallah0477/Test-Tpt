"""Stored and boundary models shared by the backend and the Runner (AD-3).

Phase 1 models plus the version envelope (AD-5). Phase 2 content models
(TestPlan, TestCode, Repair, RunResult) are added in Phase 2.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from contracts.ids import utc_now
from contracts.locators import check_args, render_locator


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware (UTC)")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]
"""ISO-8601 UTC timestamp; serialized with a trailing `Z`."""


class Model(BaseModel):
    """Base for every contract model: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- enums


class InspectionStatus(StrEnum):
    complete = "complete"
    partial = "partial"
    unreachable = "unreachable"
    timeout = "timeout"
    login_required = "login_required"


class Visibility(StrEnum):
    visible = "visible"
    hidden = "hidden"
    inaccessible = "inaccessible"


class LocatorStrategy(StrEnum):
    role = "role"
    label = "label"
    test_id = "test_id"
    css = "css"
    text = "text"


class Reliability(StrEnum):
    High = "High"
    Medium = "Medium"
    Low = "Low"


class Gate(StrEnum):
    G0 = "G0"  # target origin approved
    G1 = "G1"  # test plan approved
    G2 = "G2"  # generated code reviewed
    G3 = "G3"  # execution approved
    G4 = "G4"  # rerun approved
    G5 = "G5"  # maintenance repair approved


class ValidationOutcome(StrEnum):
    passed = "passed"
    failed_retried = "failed_retried"
    blocked = "blocked"


# ---------------------------------------------------------------- findings


class FindingRef(Model):
    """The only way to point at a Finding from outside its Inspection (AD-11)."""

    inspection_id: str
    finding_id: str = Field(pattern=r"^f_\d{3,}$")


class BBox(Model):
    x: float
    y: float
    width: float
    height: float


class Fingerprint(Model):
    """Matching inputs produced by the Runner (AD-11)."""

    role: str | None = None
    accessible_name: str | None = None
    tag: str
    type: str | None = None
    container: str | None = None
    id: str | None = None
    name: str | None = None
    data_testid: str | None = None
    label: str | None = None


LocatorArgValue = str | bool


class LocatorCandidate(Model):
    """A locator identified by (strategy, args); `expr` is display-only text."""

    strategy: LocatorStrategy
    args: dict[str, LocatorArgValue]
    expr: str = ""
    match_count: int = Field(ge=0)
    rank: int = Field(ge=1)
    reliability: Reliability

    @model_validator(mode="after")
    def _render_expr(self) -> "LocatorCandidate":
        check_args(self.strategy.value, self.args)
        self.expr = render_locator(self)
        return self

    def identity(self) -> tuple[str, tuple[tuple[str, LocatorArgValue], ...]]:
        return (self.strategy.value, tuple(sorted(self.args.items())))


class Finding(Model):
    finding_id: str = Field(pattern=r"^f_\d{3,}$")
    tag: str
    type: str | None = None
    role: str | None = None
    accessible_name: str | None = None
    label: str | None = None
    visible_text: str | None = None
    attributes: dict[str, str] = Field(
        default_factory=dict, description="DOM attributes exactly as observed (boolean attributes have value '')"
    )
    visibility: Visibility
    bbox: BBox | None = None
    container: str | None = Field(default=None, description="Containing landmark or form, e.g. form#login")
    fingerprint: Fingerprint
    locators: list[LocatorCandidate] = Field(default_factory=list)
    dom_snippet: str | None = None
    crop: str | None = Field(default=None, description="Crop image path relative to data/")


class InspectionCounts(Model):
    total: int = 0
    visible: int = 0
    hidden: int = 0
    inaccessible: int = 0


class Inspection(Model):
    inspection_id: str
    session_id: str
    requested_url: str
    final_url: str | None = None
    captured_at: UtcDatetime
    status: InspectionStatus
    reason: str | None = Field(default=None, description="Why the status is not complete, with possible causes")
    screenshot: str | None = Field(default=None, description="Screenshot path relative to data/")
    counts: InspectionCounts = Field(default_factory=InspectionCounts)
    browser_ms: int | None = None
    findings: list[Finding] = Field(default_factory=list)


# ---------------------------------------------------------------- session


class GoalEntry(Model):
    text: str
    set_at: UtcDatetime = Field(default_factory=utc_now)


class Scope(Model):
    """A Scope is bound to exactly one Inspection (AD-11)."""

    inspection_id: str | None = None
    refs: list[FindingRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_inspection(self) -> "Scope":
        for ref in self.refs:
            if ref.inspection_id != self.inspection_id:
                raise ValueError("every FindingRef in a Scope must belong to the Scope's inspection")
        return self


class ScopeFilters(Model):
    """Group filters (FR-12), stored in Session.filters. Combined with AND; empty lists don't filter.

    Semantics are implemented by backend utils/scope_filter.apply_filters() and mirrored in the UI.
    """

    container: str | None = Field(default=None, description="Exact Finding.container, e.g. form#login")
    element_types: list[str] = Field(default_factory=list, description="Match Finding.tag or Finding.type")
    include_hidden: bool = Field(default=True, description="False keeps only visible Findings")
    only_clickable: bool = False
    roles: list[str] = Field(default_factory=list, description="Match Finding.role")
    exclude_types: list[str] = Field(default_factory=list, description="Drop Findings whose tag or type is listed")
    exclude_roles: list[str] = Field(default_factory=list)


class ClarificationTurn(Model):
    clr_id: str
    question: str
    refs: list[FindingRef] = Field(default_factory=list)
    answer: str | None = None
    skipped: bool = False
    asked_at: UtcDatetime = Field(default_factory=utc_now)
    answered_at: UtcDatetime | None = None


class Session(Model):
    """Stored in sessions/{ses}/session.json, owned by v1/session (AD-20)."""

    session_id: str
    rev: int = 0
    created_at: UtcDatetime = Field(default_factory=utc_now)
    updated_at: UtcDatetime = Field(default_factory=utc_now)
    inspection_ids: list[str] = Field(default_factory=list)
    goals: list[GoalEntry] = Field(default_factory=list, description="Goal history; the last entry is current")
    scope: Scope = Field(default_factory=Scope)
    filters: ScopeFilters = Field(default_factory=ScopeFilters, description="Active group filters (FR-12)")
    confidence: float | None = Field(default=None, ge=0, le=1)
    actionable: bool = False
    clarification: list[ClarificationTurn] = Field(default_factory=list)

    @property
    def current_goal(self) -> str | None:
        return self.goals[-1].text if self.goals else None


# ---------------------------------------------------------------- approvals & versions


class VersionRef(Model):
    kind: str
    id: str
    version: int = Field(ge=1)


class OriginTarget(Model):
    origin: str


class Approval(Model):
    """One line of sessions/{ses}/approvals.jsonl, written only by gates.record() (AD-6)."""

    gate: Gate
    session_id: str
    target: VersionRef | OriginTarget
    content_sha256: str | None = None
    approved_at: UtcDatetime = Field(default_factory=utc_now)


class VersionEnvelope(Model):
    """artifacts/{kind}/{id}/v{n}.json; `version` and `content_sha256` come from store (AD-5)."""

    kind: str
    id: str
    version: int = Field(ge=1)
    session_id: str
    created_at: UtcDatetime
    created_by: str
    derived_from: list[VersionRef] = Field(default_factory=list)
    restored_from: int | None = None
    content_sha256: str
    content: dict[str, Any]


# ---------------------------------------------------------------- model usage & assistant


class ModelCallRecord(Model):
    """One line of usage/model_calls.jsonl per attempt (AD-9)."""

    call_id: str
    session_id: str
    inspection_id: str | None = None
    feature: str
    response_id: str | None = None
    attempt: int = Field(ge=1)
    role: Literal["assistant", "codegen"]
    provider: Literal["ollama", "cloud"]
    model: str
    setup: str = Field(description="Hardware / runtime or API setup, e.g. 'RTX 3060 6GB, Ollama 0.40.16'")
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    tokens_source: Literal["runtime", "estimate"]
    load_ms: int | None = None
    wait_ms: int | None = None
    response_ms: int | None = None
    started_at: UtcDatetime
    validation_outcome: ValidationOutcome
    reused: bool = False


class ResponseItem(Model):
    text: str
    refs: list[FindingRef] = Field(default_factory=list)


class ResponseSections(Model):
    """Empty sections are omitted in the UI (FR-15)."""

    observed: list[ResponseItem] = Field(default_factory=list)
    inferred: list[ResponseItem] = Field(default_factory=list)
    unverified: list[ResponseItem] = Field(default_factory=list)
    next_step: list[ResponseItem] = Field(default_factory=list)


class ResponseValidation(Model):
    outcome: ValidationOutcome
    retries: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)
    blocked_count: int = Field(default=0, ge=0)


class AssistantResponse(Model):
    """sessions/{ses}/responses/{resp}.json, written once by utils/agent_loop."""

    response_id: str
    session_id: str
    inspection_id: str | None = None
    feature: str
    created_at: UtcDatetime = Field(default_factory=utc_now)
    mode: Literal["summary", "clarification", "suggestions"] = "summary"
    sections: ResponseSections = Field(default_factory=ResponseSections)
    validation: ResponseValidation
    withheld_notice: str | None = Field(default=None, description="Shown when claims were blocked")
    call_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- errors


class ErrorBody(Model):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorEnvelope(Model):
    """Every API error response: {"error": {code, message, details}} (AD-14)."""

    error: ErrorBody
