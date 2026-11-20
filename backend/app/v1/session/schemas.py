"""Request/response-only models of v1/session (never stored)."""

from contracts.models import FindingRef, InspectionCounts, InspectionStatus, Model, ScopeFilters, UtcDatetime
from pydantic import Field


class InspectionSummary(Model):
    inspection_id: str
    requested_url: str
    captured_at: UtcDatetime
    status: InspectionStatus
    counts: InspectionCounts


class GoalRequest(Model):
    text: str = Field(min_length=1, max_length=2000)


class ScopeRequest(Model):
    """Replaces the whole Scope. Every ref must name a Finding of `inspection_id` (AD-11)."""

    inspection_id: str
    refs: list[FindingRef] = Field(default_factory=list)


class FilterPreviewRequest(Model):
    inspection_id: str
    filters: ScopeFilters = Field(default_factory=ScopeFilters)


class FilterPreview(Model):
    inspection_id: str
    finding_ids: list[str]
    count: int


class ClarificationFromResponse(Model):
    """Store the first question of a validated clarification AssistantResponse as a new turn."""

    response_id: str


class AnswerRequest(Model):
    text: str = Field(min_length=1, max_length=2000)
