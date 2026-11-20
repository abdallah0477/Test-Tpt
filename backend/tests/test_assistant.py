"""Stories 3.3-3.5: confidence, clarification, summary, suggestions, usage (fake model_client.call)."""

import json
import os

import pytest
from contracts import ClarificationTurn, GoalEntry, Scope, Session, parse_event, utc_now
from fastapi.testclient import TestClient

from app.main import app
from app.utils import confidence, model_client, store
from tests.samples import sample_inspection

INS = "ins_01JD0000000000000000000001"


def ref(finding_id: str) -> dict:
    return {"inspection_id": INS, "finding_id": finding_id}


class FakeModel:
    """Returns scripted contents in order; records the messages it got."""

    def __init__(self):
        self.contents: list[str] = []
        self.messages: list[list[dict]] = []
        self.fail: Exception | None = None

    async def call(self, role, messages, schema, *, session_id, feature, inspection_id, response_id, attempt):
        if self.fail:
            raise self.fail
        self.messages.append(messages)
        return model_client.ModelCall(
            call_id=f"call_{len(self.messages):026d}",
            session_id=session_id,
            feature=feature,
            role=role,
            provider="ollama",
            model="qwen3:4b-instruct-2507-q4_K_M",
            setup="test",
            content=self.contents.pop(0),
            started_at=utc_now(),
            inspection_id=inspection_id,
            response_id=response_id,
            attempt=attempt,
            prompt_tokens=400,
            completion_tokens=100,
            load_ms=5,
            response_ms=1200,
        )


@pytest.fixture
def fake(monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(model_client, "call", model.call)
    return model


@pytest.fixture
def client(fake):
    with TestClient(app) as c:
        yield c


class Ses:
    def __init__(self, client):
        self.client = client
        body = client.post("/api/v1/session").json()
        self.id, self.rev = body["session_id"], body["rev"]
        store.write_once(f"inspections/{INS}/inspection.json", sample_inspection(INS, self.id))

    def put(self, what, body):
        r = self.client.put(f"/api/v1/session/{self.id}/{what}", json=body, headers={"If-Match": str(self.rev)})
        assert r.status_code == 200, r.text
        self.rev = r.json()["rev"]
        return r.json()

    def post(self, path, body=None, expect=200):
        r = self.client.post(f"/api/v1/session/{self.id}/{path}", json=body, headers={"If-Match": str(self.rev)})
        assert r.status_code == expect, r.text
        if expect == 200:
            self.rev = r.json()["rev"]
        return r.json()


def run_job(client, path: str, session_id: str, **body):
    r = client.post(f"/api/v1/assistant/{path}", json={"session_id": session_id, **body})
    assert r.status_code == 202, r.text
    job = r.json()
    with client.stream("GET", f"/api/v1/assistant/events/{job['job_id']}") as stream:
        events = [parse_event(line[5:].strip()) for line in stream.iter_lines() if line.startswith("data:")]
    response = None
    if events[-1].event == "job_done":
        response = client.get(
            f"/api/v1/assistant/responses/{events[-1].data.result_id}", params={"session_id": session_id}
        ).json()
    return job, events, response


def summary_answer(finding_id="f_001") -> str:
    return json.dumps(
        {
            "observed": [{"text": "The Scope has a Password field.", "refs": [finding_id]}],
            "inferred": [{"text": "It is part of the login form.", "refs": [finding_id]}],
            "next_step": [{"text": "Test an empty password.", "refs": [finding_id]}],
        }
    )


def question(text: str, refs=(), containers=()) -> str:
    return json.dumps({"questions": [{"text": text, "refs": list(refs), "containers": list(containers)}]})


# ---------------------------------------------------------------- confidence (AD-16)


def session_with(goal: str | None, refs=("f_001",), turns=()) -> Session:
    return Session(
        session_id="ses_x",
        goals=[GoalEntry(text=goal)] if goal else [],
        scope=Scope(inspection_id=INS, refs=[ref(r) for r in refs]),
        clarification=list(turns),
    )


@pytest.mark.parametrize(
    ("goal", "actionable", "unmatched"),
    [
        ("test login", True, []),
        ("Test the Sign in button", True, []),
        ("test login with invalid email", True, []),
        ("test this page", False, []),
        ("test the search bar", False, ["search bar"]),
        ("verify the required fields of the login form", True, []),  # descriptive words aren't "unmatched"
        ("check the navigation links in the header", False, ["nav links"]),  # the sample page has no nav
        (None, False, []),
    ],
)
def test_confidence_signals(goal, actionable, unmatched):
    report = confidence.compute(session_with(goal), sample_inspection(INS, "ses_x"))
    assert report.actionable is actionable and report.unmatched_mentions == unmatched
    assert report.containers == ["form#login"] and 0 <= report.score <= 1


def test_open_question_lowers_and_answer_raises_confidence():
    inspection = sample_inspection(INS, "ses_x")
    open_turn = ClarificationTurn(clr_id="clr_1", question="Which area?")
    vague = confidence.compute(session_with("test this page", turns=[open_turn]), inspection)
    answered = ClarificationTurn(clr_id="clr_1", question="Which area?", answer="the login form")
    clear = confidence.compute(session_with("test this page", turns=[answered]), inspection)
    assert vague.signals.open_ambiguities == 1 and vague.score < clear.score and clear.actionable


def test_session_writes_recompute_confidence(client):
    s = Ses(client)
    session = s.put("goal", {"text": "test this page"})
    assert session["actionable"] is False and session["confidence"] == 0.4
    session = s.put("scope", {"inspection_id": INS, "refs": [ref("f_001")]})
    assert session["confidence"] == 0.65
    session = s.put("goal", {"text": "test login"})
    assert session["actionable"] is True and session["confidence"] == 1.0
    report = client.get(f"/api/v1/session/{s.id}/confidence").json()
    assert report["signals"]["references"] is True and report["threshold"] == 0.7


# ---------------------------------------------------------------- clarification (3.4)


def test_vague_goal_summary_asks_question_naming_areas(client, fake):
    s = Ses(client)
    s.put("scope", {"inspection_id": INS, "refs": [ref("f_001")]})
    s.put("goal", {"text": "test this page"})
    fake.contents = [
        question("What do you want to test?", refs=["f_001"]),  # generic: no page area named -> retry
        question("Which area should I focus on: form#login?", containers=["form#login"]),
    ]
    job, events, response = run_job(client, "summary", s.id)
    assert job["kind"] == "clarification" and job["needs_clarification"] is True
    steps = [e.step for e in events]
    assert steps == ["building_prompt", "calling_model", "validating", "retry_1", "calling_model", "validating", "done"]
    assert response["mode"] == "clarification" and response["validation"]["retries"] == 1
    assert "form#login" in response["sections"]["next_step"][0]["text"]
    assert '<data name="page_areas">' in fake.messages[0][1]["content"]

    session = s.post("clarification", {"response_id": response["response_id"]})
    turn = session["clarification"][0]
    assert turn["clr_id"].startswith("clr_") and turn["answer"] is None
    s.post("clarification", {"response_id": response["response_id"]}, expect=409)  # same question again

    session = s.post(f"clarification/{turn['clr_id']}/answer", {"text": "the login form"})
    assert session["actionable"] is True and session["clarification"][0]["answer"] == "the login form"
    s.post(f"clarification/{turn['clr_id']}/skip", expect=409)  # already closed

    # now actionable: the summary runs, and the earlier Q/A is in the prompt
    fake.contents = [summary_answer()]
    job, _, response = run_job(client, "summary", s.id)
    assert job["kind"] == "summary" and response["mode"] == "summary"
    assert "tester answered: the login form" in fake.messages[-1][1]["content"]


def test_unobserved_element_gets_absence_statement(client, fake):
    s = Ses(client)
    s.put("scope", {"inspection_id": INS, "refs": [ref("f_001")]})
    s.put("goal", {"text": "test the search bar"})
    fake.contents = [question("There is no search bar; do you mean the Password field?", refs=["f_001"])]
    _, _, response = run_job(client, "clarify", s.id)
    observed = response["sections"]["observed"]
    assert observed[0]["text"] == 'No element matching "search bar" was observed in this Inspection.'
    assert response["sections"]["next_step"][0]["refs"] == [ref("f_001")]
    assert '"search bar"' in fake.messages[0][1]["content"]


def test_repeated_question_is_retried(client, fake):
    s = Ses(client)
    s.put("goal", {"text": "test this page"})
    fake.contents = [question("Which area: form#login?", containers=["form#login"])]
    _, _, first = run_job(client, "clarify", s.id)
    turn = s.post("clarification", {"response_id": first["response_id"]})["clarification"][0]
    s.post(f"clarification/{turn['clr_id']}/answer", {"text": "not sure"})
    fake.contents = [
        question("Which area: form#login?", containers=["form#login"]),
        question("Inside form#login, the Password field or the Email field?", refs=["f_001", "f_003"]),
    ]
    _, _, second = run_job(client, "clarify", s.id)
    assert second["validation"]["retries"] == 1
    assert "already asked" in fake.messages[-1][-1]["content"]


def test_skip_then_summary_and_suggestions(client, fake):
    s = Ses(client)
    s.put("scope", {"inspection_id": INS, "refs": [ref("f_001")]})
    s.put("goal", {"text": "test this page"})
    fake.contents = [question("Which area: form#login?", containers=["form#login"])]
    _, _, asked = run_job(client, "summary", s.id)
    turn = s.post("clarification", {"response_id": asked["response_id"]})["clarification"][0]
    s.post(f"clarification/{turn['clr_id']}/skip")
    fake.contents = [summary_answer()]
    _, _, suggestions = run_job(client, "suggestions", s.id)
    assert suggestions["mode"] == "suggestions" and suggestions["sections"]["next_step"]
    fake.contents = [summary_answer()]
    job, _, _ = run_job(client, "summary", s.id)
    assert job["kind"] == "summary"  # skip lets the summary proceed


# ---------------------------------------------------------------- summary (3.3) and suggestions


def test_summary_retries_then_returns_sections(client, fake):
    s = Ses(client)
    s.put("scope", {"inspection_id": INS, "refs": [ref("f_001")]})
    s.put("goal", {"text": "test login"})
    fake.contents = [summary_answer("f_003"), summary_answer()]  # f_003 is outside the Scope
    job, events, response = run_job(client, "summary", s.id)
    assert job["kind"] == "summary" and events[-1].event == "job_done"
    assert "retry_1" in [e.step for e in events]
    assert response["validation"] == {"outcome": "passed", "retries": 1, "errors": [], "blocked_count": 0}
    assert response["sections"]["observed"][0]["refs"] == [ref("f_001")] and response["withheld_notice"] is None
    assert len(response["call_ids"]) == 2
    prompt = fake.messages[0][1]["content"]
    assert '"finding_id":"f_001"' in prompt and '"finding_id":"f_003"' not in prompt  # only Findings in Scope


def test_summary_needs_scope_and_inspection(client):
    s = Ses(client)
    r = client.post("/api/v1/assistant/summary", json={"session_id": s.id})
    assert r.status_code == 409 and r.json()["error"]["code"] == "scope_empty"
    empty = client.post("/api/v1/session").json()["session_id"]
    assert client.post("/api/v1/assistant/summary", json={"session_id": empty}).json()["error"]["code"] == (
        "no_inspection"
    )


def test_finding_suggestions_only_use_that_finding(client, fake):
    s = Ses(client)
    fake.contents = [summary_answer("f_003"), summary_answer("f_003"), summary_answer("f_003")]
    _, _, response = run_job(client, "suggestions", s.id, finding_ref=ref("f_001"))
    assert response["validation"]["outcome"] == "blocked" and response["withheld_notice"]
    fake.contents = [summary_answer("f_001")]
    _, _, response = run_job(client, "suggestions", s.id, finding_ref=ref("f_001"))
    assert response["mode"] == "suggestions" and response["validation"]["outcome"] == "passed"
    r = client.post("/api/v1/assistant/suggestions", json={"session_id": s.id, "finding_ref": ref("f_099")})
    assert r.status_code == 404


def test_model_unavailable(client, fake, monkeypatch):
    s = Ses(client)
    s.put("scope", {"inspection_id": INS, "refs": [ref("f_001")]})
    s.put("goal", {"text": "test login"})
    fake.fail = model_client.ModelUnavailableError("cannot reach Ollama")
    _, events, _ = run_job(client, "summary", s.id)
    assert events[-1].event == "job_failed" and events[-1].data.error.code == "model_unavailable"

    async def down():
        return model_client.ModelStatus(model="m", error="cannot reach Ollama")

    monkeypatch.setattr(model_client, "status", lambda: model_client.ModelStatus(model="m", error="down"))
    monkeypatch.setattr(model_client, "startup", down)
    r = client.post("/api/v1/assistant/summary", json={"session_id": s.id})
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"


def test_unknown_job_and_response_are_404(client):
    s = Ses(client)
    assert client.get("/api/v1/assistant/events/resp_01JD0000000000000000000000").status_code == 404
    r = client.get("/api/v1/assistant/responses/resp_01JD0000000000000000000000", params={"session_id": s.id})
    assert r.json()["error"]["code"] == "response_not_found"


# ---------------------------------------------------------------- usage (3.5)


def test_usage_grouping_and_export(client, fake):
    s = Ses(client)
    s.put("scope", {"inspection_id": INS, "refs": [ref("f_001")]})
    s.put("goal", {"text": "test login"})
    fake.contents = [summary_answer("f_099"), summary_answer()]
    _, _, response = run_job(client, "summary", s.id)
    run_job(client, "summary", s.id)  # identical request -> reuse cache, recorded reused=true

    usage = client.get(f"/api/v1/usage/{s.id}").json()
    assert [r["validation_outcome"] for r in usage["records"]] == ["failed_retried", "passed", "passed"]
    assert [r["reused"] for r in usage["records"]] == [False, False, True]
    group = usage["responses"][0]
    assert group["response_id"] == response["response_id"] and group["calls"] == 2 and group["reused_calls"] == 1
    assert group["total_tokens"] == 1000 and group["response_ms"] == 2400 and group["outcome"] == "passed"
    assert usage["total_calls"] == 2 and usage["total_tokens"] == 1000

    export = client.get(f"/api/v1/usage/{s.id}/export")
    assert export.headers["content-disposition"] == f'attachment; filename="model_calls_{s.id}.json"'
    rows = json.loads(export.content)
    assert len(rows) == 3 and set(rows[0]) >= {"call_id", "setup", "tokens_source", "load_ms", "wait_ms", "reused"}
    assert client.get("/api/v1/usage/ses_nope").status_code == 404


# ---------------------------------------------------------------- live


@pytest.mark.ollama
@pytest.mark.skipif(os.environ.get("RUN_OLLAMA_TESTS") != "1", reason="set RUN_OLLAMA_TESTS=1 for live Ollama")
def test_live_summary(monkeypatch):
    monkeypatch.setenv("TPT__OLLAMA__WARMUP", "true")
    from app.utils.config import get_config

    get_config.cache_clear()
    with TestClient(app) as client:
        import time

        for _ in range(600):
            if model_client.status().warm or model_client.status().error:
                break
            time.sleep(0.1)
        assert model_client.status().warm, model_client.status()
        s = Ses(client)
        s.put("scope", {"inspection_id": INS, "refs": [ref("f_001"), ref("f_002"), ref("f_003")]})
        s.put("goal", {"text": "test login with an invalid email"})
        job, events, response = run_job(client, "summary", s.id)
        usage = client.get(f"/api/v1/usage/{s.id}").json()
    print("\nLIVE steps:", [e.step for e in events])
    print("LIVE response:", json.dumps(response, indent=1))
    print("LIVE usage:", json.dumps(usage["records"], indent=1))
    assert events[-1].event == "job_done" and job["kind"] == "summary"
    assert response["validation"]["outcome"] in ("passed", "blocked")
