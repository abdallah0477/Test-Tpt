"""Runner worker end to end: exchange files, failure states, allowlist, reinspect (Stories 1.4, 1.10, 1.11)."""

import json
import socket

from contracts import InspectionResult, InspectRequest

from app.inspect_page import origin_of

TIMEOUT_S = 60


def run(worker, kind="inspect", **fields) -> tuple[InspectionResult, object]:
    request = InspectRequest(**{"session_id": "ses_test", "allowed_origins": [], **fields})
    _, future = worker.submit_inspect(kind, request)
    future.result(timeout=TIMEOUT_S)
    out = worker.settings.exchange_dir / "out" / request.job_id
    return InspectionResult.model_validate_json((out / "result.json").read_text()), out


def test_exchange_layout_and_done_last(worker, base_url):
    result, out = run(
        worker, job_id="ins_layout", session_id="ses_a", url=base_url + "/login.html", allowed_origins=[base_url]
    )
    ins = result.inspection
    assert (ins.inspection_id, ins.session_id) == ("ins_layout", "ses_a")
    assert ins.status == "complete" and ins.reason is None
    assert ins.requested_url == ins.final_url == base_url + "/login.html"
    assert ins.captured_at.tzinfo is not None
    assert ins.screenshot == "screenshot.png" and (out / "screenshot.png").stat().st_size > 0
    crops = sorted(p.name for p in (out / "crops").iterdir())
    assert crops == sorted(f"{f.finding_id}.png" for f in ins.findings if f.crop)
    assert all(f.crop == f"crops/{f.finding_id}.png" for f in ins.findings if f.crop)
    assert ins.counts.model_dump() == {"total": 16, "visible": 14, "hidden": 2, "inaccessible": 0}
    assert result.login_detected is True  # a password field is on the page...
    # ...but the tester asked for the login page itself, so it is not a login wall.
    files = {p.name: p.stat().st_mtime_ns for p in out.iterdir()}
    assert set(files) == {"screenshot.png", "crops", "result.json", "DONE"}
    assert files["DONE"] >= files["result.json"] >= files["screenshot.png"]
    assert json.loads((out / "result.json").read_text())["inspection"]["captured_at"].endswith("Z")


def test_runs_twice_identically(worker, base_url):
    def stable(job_id, session_id):
        result, _ = run(
            worker, job_id=job_id, session_id=session_id, url=base_url + "/login.html", allowed_origins=[base_url]
        )
        return [f.model_dump() for f in result.inspection.findings]

    assert stable("ins_det1", "ses_d1") == stable("ins_det2", "ses_d2")


def closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_unreachable_connection_refused(worker):
    url = f"http://127.0.0.1:{closed_port()}/"
    result, out = run(worker, job_id="ins_refused", url=url, allowed_origins=[url])
    ins = result.inspection
    assert ins.status == "unreachable"
    assert "ERR_CONNECTION_REFUSED" in ins.reason and "port" in ins.reason
    assert ins.findings == [] and ins.counts.total == 0 and ins.screenshot is None
    assert (out / "DONE").exists()


def test_unreachable_dns(worker):
    url = "http://no-such-host.invalid/"
    result, _ = run(worker, job_id="ins_dns", url=url, allowed_origins=[url])
    assert result.inspection.status == "unreachable"
    assert "DNS" in result.inspection.reason and result.inspection.findings == []


def test_timeout_keeps_what_loaded(worker, base_url):
    result, out = run(
        worker, job_id="ins_slow", url=base_url + "/slow", allowed_origins=[base_url], load_timeout_ms=1000
    )
    ins = result.inspection
    assert ins.status == "timeout" and "1000 ms" in ins.reason
    assert [f.attributes.get("id") for f in ins.findings] == ["early"]
    assert ins.screenshot == "screenshot.png" and (out / "DONE").exists()


def test_login_redirect_is_login_required(worker, base_url):
    result, _ = run(worker, job_id="ins_wall", url=base_url + "/account", allowed_origins=[base_url])
    ins = result.inspection
    assert ins.status == "login_required" and result.login_detected
    assert ins.final_url == base_url + "/signin.html"
    assert "Sign in by hand" in ins.reason
    assert ins.counts.total == 3  # the login form is still captured


def test_partial_when_elements_inaccessible(worker, base_url):
    result, _ = run(worker, job_id="ins_partial", url=base_url + "/overlay.html", allowed_origins=[base_url])
    ins = result.inspection
    assert ins.status == "partial"
    assert ins.counts.inaccessible == 1 and "inaccessible" in ins.reason
    assert len(ins.findings) == 1


def test_origin_allowlist_aborts_other_origins(worker, servers):
    main, other = servers
    blocked, _ = run(
        worker, job_id="ins_block", session_id="ses_b1", url=main + "/crossorigin.html", allowed_origins=[main]
    )
    assert [f.attributes.get("id") for f in blocked.inspection.findings] == ["local"]
    assert worker._contexts["ses_b1"].state.blocked == [other]

    allowed, _ = run(
        worker, job_id="ins_allow", session_id="ses_b2", url=main + "/crossorigin.html", allowed_origins=[main, other]
    )
    assert [f.attributes.get("id") for f in allowed.inspection.findings] == ["local", "injected"]


def test_navigation_to_unapproved_origin_is_reported(worker, servers):
    main, other = servers
    result, _ = run(worker, job_id="ins_nav", url=other + "/login.html", allowed_origins=[main])
    assert result.inspection.status == "unreachable"
    assert other in result.inspection.reason and "not an approved origin" in result.inspection.reason


def test_reinspect_reuses_session_context(worker, base_url):
    before, _ = run(worker, job_id="ins_r1", session_id="ses_r", url=base_url + "/whoami", allowed_origins=[base_url])
    assert [f.accessible_name for f in before.inspection.findings] == ["Please sign in"]
    context = worker._contexts["ses_r"].context

    # Stand-in for the tester signing in by hand in the visible browser.
    run(worker, job_id="ins_r2", session_id="ses_r", url=base_url + "/setcookie", allowed_origins=[base_url])
    after, _ = run(
        worker, "reinspect", job_id="ins_r3", session_id="ses_r", url=base_url + "/whoami", allowed_origins=[base_url]
    )
    assert [f.accessible_name for f in after.inspection.findings] == ["Welcome back"]
    assert worker._contexts["ses_r"].context is context

    # Another session does not see the cookie, and /close drops the context.
    other, _ = run(
        worker, job_id="ins_r4", session_id="ses_other", url=base_url + "/whoami", allowed_origins=[base_url]
    )
    assert [f.accessible_name for f in other.inspection.findings] == ["Please sign in"]
    assert worker.submit_close("ses_r").result(timeout=TIMEOUT_S) is True
    assert "ses_r" not in worker._contexts
    assert worker.submit_close("ses_r").result(timeout=TIMEOUT_S) is False


def test_fifo_queue_positions_and_events(worker, base_url):
    futures, positions = [], []
    for i in range(3):
        request = InspectRequest(
            job_id=f"ins_q{i}", session_id="ses_q", url=base_url + "/overlay.html", allowed_origins=[base_url]
        )
        position, future = worker.submit_inspect("inspect", request)
        positions.append(position)
        futures.append(future)
    for future in futures:
        future.result(timeout=TIMEOUT_S)
    assert positions == [0, 1, 2]

    events = worker.bus.history()
    done_order = [e.job_id for e in events if e.event == "job_done"]
    assert done_order == ["ins_q0", "ins_q1", "ins_q2"]
    steps = [e.step for e in worker.bus.history("ins_q1") if e.event == "job_progress"]
    assert [s for i, s in enumerate(steps) if i == 0 or steps[i - 1] != s] == [
        "load",
        "extract",
        "locators",
        "screenshot",
    ]
    first = worker.bus.history("ins_q1")
    assert first[0].event == "job_queued" and first[-1].event == "job_done"
    assert first[-1].data.inspection_status == "partial"


def test_origin_normalisation():
    assert origin_of("HTTP://Example.com:80/a?b") == "http://example.com"
    assert origin_of("https://example.com:8443/") == "https://example.com:8443"
    assert origin_of("wss://example.com/socket") == "https://example.com"
    assert origin_of("data:text/html,hi") is None
