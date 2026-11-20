"""Request/response models and model-output schemas of v1/assistant (never stored as such)."""

from typing import Literal

from contracts import FindingRef
from contracts.models import Model
from pydantic import Field

from app.utils.agent_loop import Claim


class AssistantRequest(Model):
    session_id: str


class SuggestionsRequest(Model):
    """With `finding_ref`: suggestions for that one Finding (detail panel). Without: for the Scope (after a skip)."""

    session_id: str
    finding_ref: FindingRef | None = None


class AssistantJob(Model):
    job_id: str = Field(description="Also the response_id once done; stream /api/v1/assistant/events/{job_id}")
    kind: Literal["summary", "clarification", "suggestions"]
    needs_clarification: bool = Field(
        default=False, description="True when a summary was asked but the goal isn't actionable yet"
    )
    confidence: float | None = None


# ---------------------------------------------------------------- model output schemas


class Question(Claim):
    """A clarification question; `containers` are observed page areas offered as options."""

    containers: list[str] = Field(default_factory=list)


class ClarificationOutput(Model):
    observed: list[Claim] = Field(default_factory=list, description="Grounded facts that motivate the question")
    questions: list[Question] = Field(default_factory=list, description="Exactly one question")
