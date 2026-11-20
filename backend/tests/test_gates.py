import pytest
from contracts import Gate, VersionRef

from app.utils import gates, store


def test_record_g0_appends_approval_and_origin_is_listed(data_dir):
    approval = gates.record(Gate.G0, "ses_1", origin="http://LocalHost:3000/login?x=1")
    assert approval.target.origin == "http://localhost:3000"
    lines = store.read_jsonl("sessions/ses_1/approvals.jsonl")
    assert len(lines) == 1 and lines[0]["gate"] == "G0"
    assert gates.approved_origins("ses_1") == ["http://localhost:3000"]


def test_approved_origins_are_distinct_and_per_session():
    gates.record("G0", "ses_1", origin="https://example.com/a")
    gates.record("G0", "ses_1", origin="https://example.com:443/b")
    gates.record("G0", "ses_1", origin="http://127.0.0.1:8080")
    gates.record("G0", "ses_2", origin="https://other.test")
    assert gates.approved_origins("ses_1") == ["https://example.com", "http://127.0.0.1:8080"]
    assert gates.approved_origins("ses_2") == ["https://other.test"]
    assert gates.approved_origins("ses_none") == []


def test_require_load_url_allows_approved_origin_only():
    gates.record("G0", "ses_1", origin="http://localhost:3000")
    gates.require("runner.load_url", "ses_1", "http://localhost:3000/dashboard")
    with pytest.raises(gates.GateError):
        gates.require("runner.load_url", "ses_1", "http://localhost:4000/")
    with pytest.raises(gates.GateError):
        gates.require("runner.load_url", "ses_1", "https://localhost:3000/")
    with pytest.raises(gates.GateError):
        gates.require("runner.load_url", "ses_2", "http://localhost:3000/")
    with pytest.raises(gates.GateError):
        gates.require("runner.load_url", "ses_1", "file:///etc/passwd")


def test_record_version_gate():
    target = VersionRef(kind="test_plan", id="tp_1", version=1)
    approval = gates.record("G1", "ses_1", target=target, content_sha256="ab" * 32)
    assert approval.target == target
    assert gates.approved_origins("ses_1") == []
    assert [a.gate for a in gates.approvals("ses_1")] == [Gate.G1]


def test_record_rejects_wrong_target():
    with pytest.raises(ValueError):
        gates.record("G0", "ses_1")
    with pytest.raises(ValueError):
        gates.record("G1", "ses_1", origin="http://localhost")
    with pytest.raises(ValueError):
        gates.record("G0", "ses_1", origin="not a url")


@pytest.mark.parametrize("action", ["codegen.generate", "execution.run", "execution.rerun", "maintenance.apply"])
def test_phase2_actions_fail_closed(action):
    with pytest.raises(gates.GateNotImplementedError):
        gates.require(action, "ses_1")


def test_unknown_action_fails_closed():
    with pytest.raises(gates.GateError):
        gates.require("runner.anything", "ses_1")
