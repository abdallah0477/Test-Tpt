import ast
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from contracts import (
    Approval,
    AssistantResponse,
    ClarificationTurn,
    ErrorEnvelope,
    Finding,
    FindingRef,
    Inspection,
    JobDoneEvent,
    JobFailedEvent,
    JobProgressEvent,
    JobQueuedEvent,
    LocatorCandidate,
    ModelCallRecord,
    Scope,
    ScopeFilters,
    Session,
    VersionEnvelope,
    canonical_json,
    content_sha256,
    is_id,
    new_id,
    parse_event,
    render_locator,
    ulid,
)

T0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=UTC)


def locator(strategy, args, rank=1, match_count=1, reliability="High"):
    return LocatorCandidate(strategy=strategy, args=args, match_count=match_count, rank=rank, reliability=reliability)


def sample_finding() -> Finding:
    return Finding(
        finding_id="f_001",
        tag="input",
        type="password",
        role="textbox",
        accessible_name="Password",
        label="Password",
        visible_text=None,
        attributes={"id": "password", "name": "password", "type": "password", "required": "", "minlength": "8"},
        visibility="visible",
        bbox={"x": 10, "y": 20.5, "width": 200, "height": 32},
        container="form#login",
        fingerprint={
            "role": "textbox",
            "accessible_name": "Password",
            "tag": "input",
            "type": "password",
            "container": "form#login",
            "id": "password",
            "name": "password",
            "data_testid": None,
            "label": "Password",
        },
        locators=[
            locator("label", {"text": "Password"}),
            locator("css", {"selector": "#password"}, rank=2, reliability="Medium"),
        ],
    )


def sample_inspection() -> Inspection:
    return Inspection(
        inspection_id=new_id("ins"),
        session_id=new_id("ses"),
        requested_url="http://localhost:3000/login",
        final_url="http://localhost:3000/login?next=/",
        captured_at=T0,
        status="partial",
        reason="1 element inside a cross-origin iframe",
        screenshot="inspections/ins_x/screenshot.png",
        counts={"total": 2, "visible": 1, "hidden": 0, "inaccessible": 1},
        findings=[sample_finding()],
    )


def roundtrip(model):
    raw = model.model_dump_json()
    again = type(model).model_validate_json(raw)
    assert again == model
    assert json.loads(again.model_dump_json()) == json.loads(raw)
    return json.loads(raw)


# ---------------------------------------------------------------- ids


def test_ulid_shape_and_order():
    a, b = ulid(1_000), ulid(2_000)
    assert len(a) == 26 and a < b


def test_new_id_prefix():
    sid = new_id("ses")
    assert sid.startswith("ses_") and is_id(sid, "ses") and not is_id(sid, "ins")
    with pytest.raises(ValueError):
        new_id("nope")


def test_canonical_hash_ignores_key_order():
    assert canonical_json({"b": 1, "a": [1, "é"]}) == '{"a":[1,"é"],"b":1}'.encode()
    assert content_sha256({"a": 1, "b": 2}) == content_sha256({"b": 2, "a": 1})


# ---------------------------------------------------------------- round-trips


def test_inspection_roundtrip_and_utc_z():
    data = roundtrip(sample_inspection())
    assert data["captured_at"].endswith("Z")
    assert data["findings"][0]["locators"][0]["expr"] == 'page.get_by_label("Password")'


def test_session_roundtrip():
    ins = new_id("ins")
    session = Session(
        session_id=new_id("ses"),
        inspection_ids=[ins],
        goals=[{"text": "test login", "set_at": T0}, {"text": "test invalid email", "set_at": T0}],
        scope=Scope(inspection_id=ins, refs=[FindingRef(inspection_id=ins, finding_id="f_001")]),
        confidence=0.4,
        clarification=[ClarificationTurn(clr_id=new_id("clr"), question="Which fields?", asked_at=T0)],
    )
    roundtrip(session)
    assert session.current_goal == "test invalid email"


def test_session_filters_typed_with_defaults():
    old = Session.model_validate({"session_id": "ses_x", "filters": {}})  # session.json written before ScopeFilters
    assert old.filters == ScopeFilters() and old.filters.include_hidden is True
    session = Session(session_id="ses_x", filters=ScopeFilters(container="form#login", element_types=["input"]))
    assert roundtrip(session)["filters"]["container"] == "form#login"
    with pytest.raises(ValidationError):
        ScopeFilters(colour="red")


def test_scope_refs_must_match_its_inspection():
    with pytest.raises(ValidationError):
        Scope(inspection_id="ins_a", refs=[FindingRef(inspection_id="ins_b", finding_id="f_001")])


def test_approval_roundtrip_both_targets():
    roundtrip(Approval(gate="G0", session_id="ses_x", target={"origin": "http://localhost:3000"}, approved_at=T0))
    approval = Approval(
        gate="G1",
        session_id="ses_x",
        target={"kind": "test_plan", "id": "tp_x", "version": 2},
        content_sha256="ab" * 32,
        approved_at=T0,
    )
    assert roundtrip(approval)["target"]["version"] == 2


def test_model_call_record_roundtrip():
    record = ModelCallRecord(
        call_id=new_id("call"),
        session_id="ses_x",
        inspection_id="ins_x",
        feature="assistant",
        response_id=new_id("resp"),
        attempt=1,
        role="assistant",
        provider="ollama",
        model="qwen3:4b-instruct-2507-q4_K_M",
        setup="RTX 3060 Laptop 6GB, Ollama 0.40.16",
        prompt_tokens=1200,
        completion_tokens=300,
        total_tokens=1500,
        tokens_source="runtime",
        load_ms=10,
        wait_ms=0,
        response_ms=4200,
        started_at=T0,
        validation_outcome="failed_retried",
        reused=False,
    )
    roundtrip(record)


def test_assistant_response_roundtrip():
    ref = FindingRef(inspection_id="ins_x", finding_id="f_002")
    response = AssistantResponse(
        response_id=new_id("resp"),
        session_id="ses_x",
        inspection_id="ins_x",
        feature="assistant",
        created_at=T0,
        sections={
            "observed": [{"text": "The Password field is required.", "refs": [ref]}],
            "next_step": [{"text": "Confirm which error message is expected."}],
        },
        validation={"outcome": "blocked", "retries": 2, "errors": ["unknown ref f_099"], "blocked_count": 1},
        withheld_notice="1 claim was withheld because it could not be verified.",
        call_ids=[new_id("call")],
    )
    roundtrip(response)


def test_version_envelope_and_error_roundtrip():
    roundtrip(
        VersionEnvelope(
            kind="test_plan",
            id="tp_x",
            version=1,
            session_id="ses_x",
            created_at=T0,
            created_by="tester",
            content_sha256=content_sha256({"cases": []}),
            content={"cases": []},
        )
    )
    roundtrip(ErrorEnvelope(error={"code": "rev_conflict", "message": "stale", "details": {"current_rev": 3}}))


def test_unknown_fields_and_naive_datetimes_rejected():
    with pytest.raises(ValidationError):
        FindingRef(inspection_id="ins_x", finding_id="f_001", extra=1)
    with pytest.raises(ValidationError):
        FindingRef(inspection_id="ins_x", finding_id="button-1")
    with pytest.raises(ValidationError):
        Approval(gate="G0", session_id="s", target={"origin": "x"}, approved_at=datetime(2026, 1, 1))


def test_sse_event_union_roundtrip():
    events = [
        JobQueuedEvent(job_id="ins_x", step="queue", data={"position": 0}, ts=T0),
        JobProgressEvent(job_id="ins_x", step="extract", data={"message": "Extracting", "done": 3, "total": 10}),
        JobDoneEvent(job_id="ins_x", step="done", data={"result_kind": "inspection", "result_id": "ins_x"}),
        JobFailedEvent(job_id="ins_x", step="load", data={"error": {"code": "timeout", "message": "slow page"}}),
    ]
    for event in events:
        parsed = parse_event(event.model_dump_json())
        assert type(parsed) is type(event) and parsed == event
        assert set(json.loads(event.model_dump_json())) == {"event", "job_id", "step", "status", "ts", "data"}
    with pytest.raises(ValidationError):
        parse_event('{"event": "nope", "job_id": "x", "step": "s", "status": "done", "ts": "2026-01-01T00:00:00Z"}')


# ---------------------------------------------------------------- render_locator


@pytest.mark.parametrize(
    ("strategy", "args", "expected"),
    [
        ("role", {"role": "button", "name": "Sign In"}, 'page.get_by_role("button", name="Sign In")'),
        ("role", {"role": "link"}, 'page.get_by_role("link")'),
        (
            "role",
            {"role": "checkbox", "name": "Remember me", "exact": True},
            'page.get_by_role("checkbox", name="Remember me", exact=True)',
        ),
        ("label", {"text": "Password"}, 'page.get_by_label("Password")'),
        ("test_id", {"test_id": "login-submit"}, 'page.get_by_test_id("login-submit")'),
        ("css", {"selector": 'button[type="submit"]'}, "page.locator('button[type=\"submit\"]')"),
        ("css", {"selector": "#email"}, 'page.locator("#email")'),
        ("text", {"text": "Forgot password?"}, 'page.get_by_text("Forgot password?")'),
        ("text", {"text": "Sign up", "exact": False}, 'page.get_by_text("Sign up", exact=False)'),
    ],
)
def test_render_locator(strategy, args, expected):
    assert render_locator({"strategy": strategy, "args": args}) == expected
    assert locator(strategy, args).expr == expected
    ast.parse(expected)


@pytest.mark.parametrize(
    "text",
    ['He said "hi"', "it's", "both ' and \"", "back\\slash", "new\nline", "tab\there", "ünïcødé", "\x00"],
)
def test_render_locator_escaping_is_valid_python(text):
    expr = render_locator({"strategy": "text", "args": {"text": text}})
    call = ast.parse(expr, mode="eval").body
    assert ast.literal_eval(call.args[0]) == text


def test_render_locator_rejects_bad_args():
    with pytest.raises(ValueError):
        render_locator({"strategy": "xpath", "args": {"selector": "//a"}})
    with pytest.raises(ValueError):
        render_locator({"strategy": "role", "args": {"name": "x"}})
    with pytest.raises(ValueError):
        render_locator({"strategy": "css", "args": {"selector": "a", "nth": "1"}})
    with pytest.raises(ValidationError):
        locator("label", {"text": ""})


def test_locator_identity_ignores_arg_order():
    a = locator("role", {"role": "button", "name": "Go"})
    b = locator("role", {"name": "Go", "role": "button"}, rank=3, match_count=2, reliability="Low")
    assert a.identity() == b.identity()
