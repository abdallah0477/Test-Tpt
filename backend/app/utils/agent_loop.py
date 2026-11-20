"""Hand-written agent loop: schema output -> validate -> retry -> block (AD-7, AD-9, AD-10).

    result = await agent_loop.run(feature, schema, prompt_parts, scope, session_id=...)

- `schema` is a Model whose top-level `list[Claim]` (or Claim subclass) fields are the
  claims, e.g. AnswerSections. Fields named observed/inferred/unverified/next_step map
  to those response sections; any other claim field (e.g. clarification `questions`)
  is stored in `next_step`. An answer must contain at least one claim.
- `check(output)` is an optional feature hook for extra rules; it returns
  (field, index, message) tuples, index None for whole-answer problems.
- `preface` holds backend-authored, deterministic items (e.g. "no such element was
  observed") that are added to the response as they are; they aren't model output.
- `progress(step, message, done, total)` reports building_prompt, calling_model,
  validating and retry_N for SSE; nothing is streamed from the model.
- Validation per claim: schema structure, every FindingRef exists in the Inspection
  and is in Scope, every quote (structured `quotes` and `name="value"` in the text)
  matches the cited Finding exactly, and prose quotes such as "the ID 'pw'" or
  "label \"Email\"" are checked the same way; `observed` claims must cite at least one ref.
- On failure the model is called again with the errors fed back (config
  assistant.max_retries, default 2). After the last attempt failing claims are
  removed and a withheld notice is added.
- Each attempt gets one usage record, written after its validation.
- The loop owns response_id and the reuse cache: an identical request in the same (only passed answers are cached)
  Session returns the stored response and is recorded with reused=true.
- The AssistantResponse is written once to sessions/{ses}/responses/{resp}.json.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Literal, get_args, get_origin

from contracts import (
    AssistantResponse,
    Finding,
    FindingRef,
    Inspection,
    ResponseItem,
    ResponseSections,
    ResponseValidation,
    ValidationOutcome,
    content_sha256,
    new_id,
)
from contracts.models import Model
from pydantic import BaseModel, Field, ValidationError

from app.utils import model_client, prompting, store
from app.utils.config import get_config

log = logging.getLogger("app.agent_loop")

SECTIONS = ("observed", "inferred", "unverified", "next_step")
_TEXT_QUOTE = re.compile(r'\b([A-Za-z_][\w:.-]*)\s*=\s*"([^"]*)"')
_FINDING_FIELDS = ("tag", "type", "role", "accessible_name", "label", "visible_text", "container")

# Prose quotes: an attribute word followed by a quoted value, e.g. "has the ID 'pw'",
# "label 'Email'", 'placeholder "you@example.com"', "with the text 'Forgot password?'".
# Only quotes right after one of these words are checked; other quoted prose is left alone.
_PROSE_ATTRS = {
    "accessible name": ("accessible_name", "aria-label"),
    "aria-label": ("aria-label", "accessible_name"),
    "data-testid": ("data-testid",),
    "test id": ("data-testid",),
    "placeholder": ("placeholder",),
    "label": ("label", "accessible_name", "aria-label"),
    "name": ("name", "accessible_name"),
    "id": ("id",),
    "type": ("type",),
    "text": ("visible_text", "accessible_name"),
    "title": ("title",),
    "role": ("role",),
}
_PROSE_QUOTE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(k) for k in _PROSE_ATTRS), key=len, reverse=True)) + r")\b"
    r"(?:\s+(?:of|is|as|set\s+to|equal\s+to|value|attribute))*\s*[:=]?\s*"
    r"(?:'([^']+)'|\"([^\"]+)\"|\u201c([^\u201d]+)\u201d|\u2018([^\u2019]+)\u2019)",
    re.IGNORECASE,
)
NO_ANSWER_NOTICE = "The assistant couldn't produce a grounded answer. Retry to ask again."


# ---------------------------------------------------------------- model output schema


class Quote(Model):
    """An attribute value the claim quotes; must equal the Finding's value exactly."""

    finding_id: str = Field(pattern=r"^f_\d{3,}$")
    attribute: str = Field(description="DOM attribute name, or tag/type/role/accessible_name/label/visible_text")
    value: str


FindingId = Annotated[str, Field(pattern=r"^f_\d{3,}$")]


class Claim(Model):
    """Model-facing claim. `refs` are finding_ids of the one Inspection the Scope is bound to (AD-11);
    the loop turns them into FindingRefs in the stored response. (A 4B model cannot reliably copy
    26-character inspection ULIDs, so it is never asked to.)"""

    text: str
    refs: list[FindingId] = Field(default_factory=list, description="finding_id values such as f_001")
    quotes: list[Quote] = Field(default_factory=list)


class AnswerSections(Model):
    """Default output schema; features may subclass it to add fields."""

    observed: list[Claim] = Field(default_factory=list, description="Facts seen on the page; each cites refs")
    inferred: list[Claim] = Field(default_factory=list)
    unverified: list[Claim] = Field(default_factory=list)
    next_step: list[Claim] = Field(default_factory=list)


@dataclass
class LoopScope:
    """The Inspection and Scope the answer must stay within. Empty refs = the whole Inspection."""

    inspection: Inspection
    refs: list[FindingRef] = field(default_factory=list)

    def in_scope(self) -> dict[str, Finding]:
        findings = {f.finding_id: f for f in self.inspection.findings}
        if not self.refs:
            return findings
        return {r.finding_id: findings[r.finding_id] for r in self.refs if r.finding_id in findings}


@dataclass
class LoopResult:
    response: AssistantResponse
    output: BaseModel | None  # validated output after blocking (None if nothing parsed)
    reused: bool = False


# ---------------------------------------------------------------- validation


def _values(finding: Finding, name: str) -> list[str]:
    values = []
    if name in finding.attributes:
        values.append(finding.attributes[name])
    if name in _FINDING_FIELDS and getattr(finding, name) is not None:
        values.append(str(getattr(finding, name)))
    return values


def prose_quotes(text: str) -> list[tuple[str, str]]:
    """(attribute word, quoted value) pairs found in claim prose."""
    found = []
    for match in _PROSE_QUOTE.finditer(text):
        value = next(v for v in match.groups()[1:] if v is not None)
        if value != value.strip():  # "name' set to '..." spans two quotes of different values: not a quote
            continue
        found.append((" ".join(match.group(1).lower().split()), value))
    return found


def _prose_matches(finding: Finding, word: str, value: str) -> bool:
    """The quoted value equals one of the Finding's values for that word (exact, after trimming)."""
    value = value.strip()
    candidates = [v for key in _PROSE_ATTRS[word] for v in _values(finding, key)]
    if word in ("id", "name") and finding.container:  # "the form with ID 'login'" -> container form#login
        candidates += re.findall(r"[#=]([\w-]+)", finding.container)
    return any(c.strip() == value for c in candidates)


def _check_quote(finding: Finding, name: str, value: str) -> str | None:
    actual = _values(finding, name)
    if not actual:
        return f'{finding.finding_id} has no "{name}"'
    if value not in actual:
        return f'{name}="{value}" does not match {finding.finding_id} ({name}="{actual[0]}")'
    return None


def check_claim(claim: Claim, scope: LoopScope, section: str) -> list[str]:
    errors = []
    inspection = scope.inspection
    known = {f.finding_id: f for f in inspection.findings}
    allowed = scope.in_scope()
    cited: list[Finding] = []
    for finding_id in claim.refs:
        if finding_id not in known:
            errors.append(f"{finding_id} is not a Finding of this Inspection")
        elif finding_id not in allowed:
            errors.append(f"{finding_id} is not in the Scope; cite only finding_ids from the findings data")
        else:
            cited.append(known[finding_id])
    if section == "observed" and not claim.refs:
        errors.append("an observed claim must cite at least one FindingRef")
    for quote in claim.quotes:
        if quote.finding_id not in allowed:
            errors.append(f"quote cites {quote.finding_id}, which is not a Finding in the Scope")
        elif error := _check_quote(allowed[quote.finding_id], quote.attribute, quote.value):
            errors.append(error)
    for word, value in prose_quotes(claim.text):
        if not cited:
            errors.append(f"the text quotes {word} '{value}' but cites no Finding")
        elif not any(_prose_matches(f, word, value) for f in cited):
            errors.append(f"{word} '{value}' does not match any cited Finding exactly")
    for name, value in _TEXT_QUOTE.findall(claim.text):
        if not cited:
            errors.append(f'the text quotes {name}="{value}" but cites no Finding')
        elif all(_check_quote(f, name, value) for f in cited):
            errors.append(f'{name}="{value}" does not match any cited Finding exactly')
    return errors


Check = Callable[[BaseModel], list[tuple[str | None, int | None, str]]]
Progress = Callable[[str, str, int | None, int | None], None]


def claim_fields(schema: type[BaseModel] | BaseModel) -> list[str]:
    """Top-level fields annotated as list[Claim] (or a Claim subclass)."""
    model = schema if isinstance(schema, type) else type(schema)
    names = []
    for name, info in model.model_fields.items():
        args = get_args(info.annotation)
        if get_origin(info.annotation) is list and args and isinstance(args[0], type) and issubclass(args[0], Claim):
            names.append(name)
    return names


def validate(content: str, schema: type[BaseModel], scope: LoopScope, check: Check | None = None):
    """Returns (output | None, errors, {(field, index), ...} of failing claims)."""
    try:
        output = schema.model_validate_json(content)
    except ValidationError as exc:
        errors = [f"schema: {'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:10]]
        return None, errors or ["schema: invalid JSON"], set()
    errors, bad = [], set()
    if not any(getattr(output, name) for name in claim_fields(output)):
        errors.append("the answer contains no claims")
    for name in claim_fields(output):
        for index, claim in enumerate(getattr(output, name)):
            claim_errors = check_claim(claim, scope, name)
            if claim_errors:
                bad.add((name, index))
                errors.extend(f"{name}[{index}]: {e}" for e in claim_errors)
    for name, index, message in check(output) if check else []:
        if name is None or index is None:
            errors.append(message)
        else:
            bad.add((name, index))
            errors.append(f"{name}[{index}]: {message}")
    return output, errors, bad


def _block(output: BaseModel, bad: set[tuple[str, int]]) -> BaseModel:
    kept = output.model_copy()
    for name in claim_fields(output):
        setattr(kept, name, [c for i, c in enumerate(getattr(output, name)) if (name, i) not in bad])
    return kept


# ---------------------------------------------------------------- loop


_cache: dict[str, tuple[str, model_client.ModelCall, ValidationOutcome, BaseModel | None]] = {}


def response_path(session_id: str, response_id: str) -> str:
    return f"sessions/{session_id}/responses/{response_id}.json"


def allocate_response_id() -> str:
    """A response_id for a job that will call run(response_id=...); the loop is the only allocator (AD-9)."""
    return new_id("resp")


def _sections(
    output: BaseModel | None, preface: dict[str, list[ResponseItem]] | None, inspection_id: str
) -> ResponseSections:
    items: dict[str, list[ResponseItem]] = {name: list((preface or {}).get(name, [])) for name in SECTIONS}
    for name in claim_fields(output) if output is not None else []:
        target = name if name in SECTIONS else "next_step"
        for claim in getattr(output, name):
            refs = [FindingRef(inspection_id=inspection_id, finding_id=f) for f in dict.fromkeys(claim.refs)]
            items[target].append(ResponseItem(text=claim.text, refs=refs))
    return ResponseSections(**items)


def clear_cache() -> None:
    _cache.clear()


async def run(
    feature: str,
    schema: type[BaseModel],
    parts: prompting.PromptParts,
    scope: LoopScope,
    *,
    session_id: str,
    role: Literal["assistant", "codegen"] = "assistant",
    mode: Literal["summary", "clarification", "suggestions"] = "summary",
    check: Check | None = None,
    preface: dict[str, list[ResponseItem]] | None = None,
    response_id: str | None = None,
    progress: Progress | None = None,
) -> LoopResult:
    def report(step: str, message: str, done: int | None = None, total: int | None = None) -> None:
        if progress is not None:
            progress(step, message, done, total)

    report("building_prompt", "building the prompt")
    config = get_config()
    settings = getattr(config.models, role)
    inspection_id = scope.inspection.inspection_id
    parts.inspection_id = parts.inspection_id or inspection_id
    if not parts.findings:
        parts.findings = list(scope.in_scope().values())
    messages, budget = prompting.build_messages(parts, settings.num_ctx, settings.num_predict)
    json_schema = schema.model_json_schema()

    key = content_sha256(
        {
            "session_id": session_id,
            "feature": feature,
            "role": role,
            "mode": mode,
            "model": [settings.provider, settings.model, settings.temperature, settings.num_ctx],
            "schema": json_schema,
            "messages": messages,
            "scope": [r.model_dump() for r in scope.refs],
            "preface": {k: [i.model_dump(mode="json") for i in v] for k, v in (preface or {}).items()},
        }
    )
    if key in _cache and store.exists(response_path(session_id, _cache[key][0])):
        response_id, last_call, outcome, output = _cache[key]
        model_client.record(last_call, outcome, reused=True)
        stored = AssistantResponse.model_validate(store.read_json(response_path(session_id, response_id)))
        return LoopResult(response=stored, output=output, reused=True)

    response_id = response_id or allocate_response_id()
    attempts = 1 + config.assistant.max_retries
    call_ids: list[str] = []
    output: BaseModel | None = None
    errors: list[str] = []
    bad: set[tuple[str, int]] = set()
    outcome = ValidationOutcome.passed
    call = None
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            report(f"retry_{attempt - 1}", f"retry {attempt - 1} of {attempts - 1}", attempt - 1, attempts - 1)
        report("calling_model", f"calling the model (attempt {attempt})", attempt, attempts)
        call = await model_client.call(
            role,
            messages,
            json_schema,
            session_id=session_id,
            feature=feature,
            inspection_id=inspection_id,
            response_id=response_id,
            attempt=attempt,
        )
        call_ids.append(call.call_id)
        report("validating", "validating the answer against the Inspection", attempt, attempts)
        output, errors, bad = validate(call.content, schema, scope, check)
        if not errors:
            outcome = ValidationOutcome.passed
            model_client.record(call, outcome)
            break
        if attempt < attempts:
            model_client.record(call, ValidationOutcome.failed_retried)
            messages = [*messages, {"role": "assistant", "content": call.content}, prompting.feedback_message(errors)]
            continue
        outcome = ValidationOutcome.blocked
        model_client.record(call, outcome)
        log.warning("claims blocked after retries", extra={"session_id": session_id})

    blocked_count = 0
    if outcome is ValidationOutcome.blocked and output is not None:
        blocked_count = len(bad)
        output = _block(output, bad)
    sections = _sections(output, preface, inspection_id)
    remaining = sum(len(getattr(output, name)) for name in claim_fields(output)) if output is not None else 0
    notice = None
    if outcome is ValidationOutcome.blocked:
        notice = (
            NO_ANSWER_NOTICE
            if remaining == 0
            else f"{blocked_count} claim(s) were withheld because they could not be verified against the Inspection."
        )
    response = AssistantResponse(
        response_id=response_id,
        session_id=session_id,
        inspection_id=inspection_id,
        feature=feature,
        mode=mode,
        sections=sections,
        validation=ResponseValidation(
            outcome=outcome,
            retries=len(call_ids) - 1,
            errors=errors if outcome is ValidationOutcome.blocked else [],
            blocked_count=blocked_count,
        ),
        withheld_notice=notice,
        call_ids=call_ids,
    )
    store.write_once(response_path(session_id, response_id), response)
    if budget.findings_omitted:
        log.info("findings omitted to fit the context window", extra={"session_id": session_id})
    if call is not None and outcome is ValidationOutcome.passed:  # Retry after a block must call the model again
        _cache[key] = (response_id, call, outcome, output)
    return LoopResult(response=response, output=output)
