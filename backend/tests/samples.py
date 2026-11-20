"""Shared test data: a stored-looking Inspection with a login form."""

from contracts import Inspection, InspectionResult, utc_now

PNG = b"\x89PNG\r\n\x1a\n fake"


def sample_result(job_id: str, session_id: str, url: str, status: str = "complete") -> InspectionResult:
    finding = {
        "finding_id": "f_001",
        "tag": "input",
        "type": "password",
        "label": "Password",
        "attributes": {"id": "pw", "type": "password", "required": ""},
        "visibility": "visible",
        "bbox": {"x": 1, "y": 2, "width": 100, "height": 20},
        "container": "form#login",
        "fingerprint": {"tag": "input", "type": "password", "id": "pw", "label": "Password"},
        "locators": [
            {"strategy": "label", "args": {"text": "Password"}, "match_count": 1, "rank": 1, "reliability": "High"},
            {"strategy": "css", "args": {"selector": "#pw"}, "match_count": 1, "rank": 2, "reliability": "Medium"},
        ],
        "crop": "crops/f_001.png",
    }
    button = {
        "finding_id": "f_002",
        "tag": "button",
        "role": "button",
        "accessible_name": "Sign in",
        "visibility": "hidden",
        "fingerprint": {"tag": "button", "role": "button", "accessible_name": "Sign in"},
    }
    inspection = Inspection(
        inspection_id=job_id,
        session_id=session_id,
        requested_url=url,
        final_url=url + "#final",
        captured_at=utc_now(),
        status=status,
        screenshot="screenshot.png",
        counts={"total": 2, "visible": 1, "hidden": 1},
        browser_ms=321,
        findings=[finding, button],
    )
    return InspectionResult(inspection=inspection)


def sample_inspection(inspection_id: str, session_id: str, url: str = "http://localhost:5000/login") -> Inspection:
    """Three Findings: f_001 password input (visible, in form#login), f_002 hidden button, f_003 email input."""
    inspection = sample_result(inspection_id, session_id, url).inspection
    email = {
        "finding_id": "f_003",
        "tag": "input",
        "type": "email",
        "label": "Email",
        "attributes": {"id": "email", "type": "email", "placeholder": "you@example.com"},
        "visibility": "visible",
        "container": "form#login",
        "fingerprint": {"tag": "input", "type": "email", "id": "email", "label": "Email"},
    }
    inspection.findings[1].container = "form#login"
    inspection.findings.append(type(inspection.findings[0]).model_validate(email))
    return inspection
