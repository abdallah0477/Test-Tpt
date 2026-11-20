"""Stories 2.1-2.3: goal history, Scope, filters (v1/session, If-Match)."""

import pytest
from contracts import ScopeFilters, Session
from fastapi.testclient import TestClient

from app.main import app
from app.utils import store
from app.utils.scope_filter import apply_filters, is_clickable
from tests.samples import sample_inspection

INS = "ins_01JD0000000000000000000001"
OTHER = "ins_01JD0000000000000000000002"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def session_id(client) -> str:
    session_id = client.post("/api/v1/session").json()["session_id"]
    store.write_once(f"inspections/{INS}/inspection.json", sample_inspection(INS, session_id))
    store.write_once(f"inspections/{OTHER}/inspection.json", sample_inspection(OTHER, session_id))
    return session_id


def put(client, session_id: str, what: str, body: dict, rev: int | str | None):
    headers = {} if rev is None else {"If-Match": str(rev)}
    return client.put(f"/api/v1/session/{session_id}/{what}", json=body, headers=headers)


def ref(finding_id: str, inspection_id: str = INS) -> dict:
    return {"inspection_id": inspection_id, "finding_id": finding_id}


# ---------------------------------------------------------------- goal (2.1)


def test_goal_history_and_scope_kept(client, session_id):
    r = put(client, session_id, "scope", {"inspection_id": INS, "refs": [ref("f_001")]}, 1)
    assert r.status_code == 200 and r.headers["etag"] == "2"
    r = put(client, session_id, "goal", {"text": "test login"}, 2)
    r = put(client, session_id, "goal", {"text": "test invalid email"}, '"3"')
    assert r.status_code == 200
    session = Session.model_validate(r.json())
    assert [g.text for g in session.goals] == ["test login", "test invalid email"]
    assert session.current_goal == "test invalid email" and session.rev == 4
    assert session.scope.refs[0].finding_id == "f_001"
    assert client.get(f"/api/v1/session/{session_id}").json()["goals"][0]["set_at"].endswith("Z")


def test_stale_rev_is_409_and_missing_if_match_is_428(client, session_id):
    assert put(client, session_id, "goal", {"text": "a"}, 1).status_code == 200
    stale = put(client, session_id, "goal", {"text": "b"}, 1)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "rev_conflict"
    assert put(client, session_id, "goal", {"text": "b"}, None).json()["error"]["code"] == "if_match_required"
    assert put(client, session_id, "goal", {"text": "b"}, "abc").status_code == 400
    assert put(client, session_id, "goal", {"text": "  "}, 2).json()["error"]["code"] == "invalid_goal"
    assert [g["text"] for g in client.get(f"/api/v1/session/{session_id}").json()["goals"]] == ["a"]


# ---------------------------------------------------------------- scope (2.2)


def test_scope_validates_refs_and_dedupes(client, session_id):
    body = {"inspection_id": INS, "refs": [ref("f_001"), ref("f_003"), ref("f_001")]}
    session = put(client, session_id, "scope", body, 1).json()
    assert [r["finding_id"] for r in session["scope"]["refs"]] == ["f_001", "f_003"]

    bad = put(client, session_id, "scope", {"inspection_id": INS, "refs": [ref("f_099")]}, 2)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_scope"
    mixed = put(client, session_id, "scope", {"inspection_id": INS, "refs": [ref("f_001", OTHER)]}, 2)
    assert mixed.status_code == 422
    missing = put(client, session_id, "scope", {"inspection_id": "ins_01JD0000000000000000000009", "refs": []}, 2)
    assert missing.json()["error"]["code"] == "inspection_not_found"

    replaced = put(client, session_id, "scope", {"inspection_id": OTHER, "refs": [ref("f_002", OTHER)]}, 2).json()
    assert replaced["scope"] == {"inspection_id": OTHER, "refs": [ref("f_002", OTHER)]}


def test_scope_rejects_inspection_of_another_session(client, session_id):
    other_session = client.post("/api/v1/session").json()["session_id"]
    r = put(client, other_session, "scope", {"inspection_id": INS, "refs": []}, 1)
    assert r.status_code == 422 and r.json()["error"]["code"] == "inspection_not_in_session"


# ---------------------------------------------------------------- filters (2.3)


def test_filters_stored_and_preview(client, session_id):
    filters = {"container": "form#login", "element_types": ["input"]}
    session = put(client, session_id, "filters", filters, 1).json()
    assert session["filters"]["container"] == "form#login" and session["filters"]["include_hidden"] is True
    preview = client.post(f"/api/v1/session/{session_id}/filter-preview", json={"inspection_id": INS})
    assert preview.json()["count"] == 3  # no filters: every recorded Finding
    preview = client.post(
        f"/api/v1/session/{session_id}/filter-preview", json={"inspection_id": INS, "filters": filters}
    ).json()
    assert preview == {"inspection_id": INS, "finding_ids": ["f_001", "f_003"], "count": 2}
    # apply to the Scope, then remove one Finding
    body = {"inspection_id": INS, "refs": [ref(i) for i in preview["finding_ids"] if i != "f_003"]}
    session = put(client, session_id, "scope", body, 2).json()
    assert [r["finding_id"] for r in session["scope"]["refs"]] == ["f_001"]
    assert session["filters"]["element_types"] == ["input"]


def test_apply_filters_and_logic():
    findings = sample_inspection(INS, "ses_x").findings  # f_001 password, f_002 hidden button, f_003 email
    ids = lambda fs: [f.finding_id for f in fs]  # noqa: E731
    assert ids(apply_filters(findings, ScopeFilters())) == ["f_001", "f_002", "f_003"]
    assert ids(apply_filters(findings, ScopeFilters(element_types=["INPUT"]))) == ["f_001", "f_003"]
    assert ids(apply_filters(findings, ScopeFilters(element_types=["password"]))) == ["f_001"]
    assert ids(apply_filters(findings, ScopeFilters(include_hidden=False))) == ["f_001", "f_003"]
    assert ids(apply_filters(findings, ScopeFilters(only_clickable=True))) == ["f_002"]
    assert ids(apply_filters(findings, ScopeFilters(only_clickable=True, include_hidden=False))) == []
    assert ids(apply_filters(findings, ScopeFilters(roles=["button"]))) == ["f_002"]
    assert ids(apply_filters(findings, ScopeFilters(exclude_types=["email"]))) == ["f_001", "f_002"]
    assert ids(apply_filters(findings, ScopeFilters(exclude_roles=["button"]))) == ["f_001", "f_003"]
    assert ids(apply_filters(findings, ScopeFilters(container="nav"))) == []
    disabled = findings[1].model_copy(update={"attributes": {"disabled": ""}})
    assert not is_clickable(disabled)
