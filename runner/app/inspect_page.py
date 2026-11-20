"""One inspection: load the page, extract Findings, verify locators, take screenshots.

Runs inside the worker thread only (Playwright sync API). Writes the files of
out/{job_id}/ and returns the InspectionResult; the worker writes result.json
and the DONE marker afterwards.

Status (checked in this order):
- unreachable:    navigation failed (DNS, connection refused, blocked origin ...); no Findings.
- timeout:        the page did not finish loading within load_timeout_ms, or the job ran out
                  of time; whatever was already in the DOM is still extracted.
- login_required: a login wall (see `looks_like_login_wall`); login_detected is set.
- partial:        some elements could not be inspected (inaccessible, extraction errors,
                  or visible iframes whose content is not extracted).
- complete:       everything else.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from contracts import Finding, Inspection, InspectionCounts, InspectionResult, InspectionStatus, utc_now
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app import extract, locators

Emit = Callable[[str, str], None]  # (step, message)

LOGIN_PATH = re.compile(r"(log-?in|sign-?in|signon|auth|sso)", re.IGNORECASE)
FEW_ELEMENTS = 8
CROP_PADDING = 8
NETWORK_IDLE_MS = 2000

UNREACHABLE_CAUSES = {
    "ERR_NAME_NOT_RESOLVED": "DNS lookup failed: the host name does not exist, is misspelled, or there is no network.",
    "ERR_CONNECTION_REFUSED": (
        "Connection refused: nothing is listening on that host and port (wrong port, or the server is not "
        "running). For a site on your own laptop use host.docker.internal instead of localhost."
    ),
    "ERR_CONNECTION_TIMED_OUT": "The connection timed out: the host is down or a firewall drops the traffic.",
    "ERR_ADDRESS_UNREACHABLE": "The address is unreachable from the Runner container (wrong IP or network).",
    "ERR_INTERNET_DISCONNECTED": "The Runner has no network connection.",
    "ERR_CONNECTION_RESET": "The server reset the connection (it crashed, or speaks another protocol on that port).",
    "ERR_UNSAFE_PORT": "The browser refuses this port because it belongs to another protocol; use a web port.",
    "ERR_SSL_PROTOCOL_ERROR": "TLS handshake failed: the port may not serve HTTPS (try http://).",
}
DEFAULT_CAUSES = "Possible causes: wrong host name (DNS), wrong port, the server is not running, or a TLS problem."


class JobDeadline:
    """Hard time limit for the whole job (JOB_TIMEOUT_MS)."""

    def __init__(self, timeout_ms: int) -> None:
        self.end = time.monotonic() + timeout_ms / 1000

    def expired(self) -> bool:
        return time.monotonic() > self.end


@dataclass
class SessionState:
    """What the route handler needs: the allowed origins and what it blocked."""

    allowed: set[str] = field(default_factory=set)
    blocked: list[str] = field(default_factory=list)


def origin_of(url: str) -> str | None:
    """scheme://host[:port] for http(s)/ws(s) URLs, default ports dropped; None for other schemes."""
    parts = urlsplit(url)
    scheme = {"ws": "http", "wss": "https"}.get(parts.scheme.lower(), parts.scheme.lower())
    if scheme not in ("http", "https") or not parts.hostname:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    default = 80 if scheme == "http" else 443
    host = parts.hostname.lower()
    if ":" in host:  # IPv6
        host = f"[{host}]"
    return f"{scheme}://{host}" if port in (None, default) else f"{scheme}://{host}:{port}"


def unreachable_reason(error: PlaywrightError, state: SessionState) -> str:
    message = str(error)
    match = re.search(r"net::(ERR_[A-Z_]+)", message)
    code = match.group(1) if match else None
    if code == "ERR_BLOCKED_BY_CLIENT":
        where = state.blocked[-1] if state.blocked else "another origin"
        return (
            f"The page navigated to {where}, which is not an approved origin. Approve that origin (G0) "
            "and inspect again."
        )
    if code and code.startswith("ERR_CERT"):
        return f"Unreachable ({code}): the site's TLS certificate is invalid or self-signed."
    if code in UNREACHABLE_CAUSES:
        return f"Unreachable ({code}): {UNREACHABLE_CAUSES[code]}"
    first_line = message.splitlines()[0] if message else "unknown error"
    return f"Unreachable ({code or first_line}). {DEFAULT_CAUSES}"


def looks_like_login_wall(findings: list[Finding], requested_url: str, final_url: str) -> tuple[bool, bool]:
    """Return (login_detected, login_required).

    login_detected: a visible password field, or a redirect to a login-like path.
    login_required: a redirect to a login-like path, or a visible password field with few
    other visible elements on a page whose own URL is not a login page (so inspecting a
    login page on purpose still gives `complete`).
    """
    requested_path = urlsplit(requested_url).path
    final_path = urlsplit(final_url).path
    redirected_to_login = final_path != requested_path and bool(LOGIN_PATH.search(final_path))
    visible = [f for f in findings if f.visibility == "visible"]
    has_password = any(f.attributes.get("type", "").lower() == "password" for f in visible)
    requested_is_login = bool(LOGIN_PATH.search(requested_path))
    detected = has_password or redirected_to_login
    required = redirected_to_login or (has_password and len(visible) <= FEW_ELEMENTS and not requested_is_login)
    return detected, required


def count(findings: list[Finding]) -> InspectionCounts:
    def n(state: str) -> int:
        return sum(1 for f in findings if f.visibility == state)

    return InspectionCounts(
        total=len(findings), visible=n("visible"), hidden=n("hidden"), inaccessible=n("inaccessible")
    )


def take_crops(page: Any, findings: list[Finding], out_dir: Path, max_crops: int, deadline: JobDeadline) -> None:
    """crops/{finding_id}.png around each rendered Finding (visible or inaccessible)."""
    size = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.scrollHeight]")
    page_w, page_h = max(size[0], 1), max(size[1], 1)
    crops_dir = out_dir / "crops"
    crops_dir.mkdir(exist_ok=True)
    taken = 0
    for finding in findings:
        if taken >= max_crops or deadline.expired():
            return
        box = finding.bbox
        if box is None or finding.visibility == "hidden":
            continue
        x = max(box.x - CROP_PADDING, 0)
        y = max(box.y - CROP_PADDING, 0)
        width = min(box.x + box.width + CROP_PADDING, page_w) - x
        height = min(box.y + box.height + CROP_PADDING, page_h) - y
        if width < 1 or height < 1:
            continue
        path = crops_dir / f"{finding.finding_id}.png"
        try:
            page.screenshot(path=str(path), full_page=True, clip={"x": x, "y": y, "width": width, "height": height})
        except PlaywrightError:
            continue
        finding.crop = f"crops/{finding.finding_id}.png"
        taken += 1


def inspect(
    page: Any,
    *,
    job_id: str,
    session_id: str,
    url: str,
    load_timeout_ms: int,
    out_dir: Path,
    state: SessionState,
    emit: Emit,
    deadline: JobDeadline,
    max_crops: int,
) -> InspectionResult:
    started = time.monotonic()
    captured_at = utc_now()
    status: InspectionStatus | None = None
    reasons: list[str] = []

    def result(findings: list[Finding], final_url: str | None, screenshot: str | None, login: bool = False):
        inspection = Inspection(
            inspection_id=job_id,
            session_id=session_id,
            requested_url=url,
            final_url=final_url,
            captured_at=captured_at,
            status=status or InspectionStatus.complete,
            reason=" ".join(reasons) or None,
            screenshot=screenshot,
            counts=count(findings),
            browser_ms=int((time.monotonic() - started) * 1000),
            findings=findings,
        )
        return InspectionResult(inspection=inspection, login_detected=login)

    # ---- load
    emit("load", f"Loading {url}")
    state.blocked.clear()
    try:
        page.goto(url, wait_until="load", timeout=load_timeout_ms)
    except PlaywrightTimeoutError:
        status = InspectionStatus.timeout
        reasons.append(
            f"The page did not finish loading within {load_timeout_ms} ms (inspection.load_timeout_ms). "
            "Showing what had loaded by then."
        )
        try:
            page.evaluate("window.stop()")
        except PlaywrightError:
            pass
    except PlaywrightError as error:
        status = InspectionStatus.unreachable
        reasons.append(unreachable_reason(error, state))
        emit("load", "Page unreachable")
        return result([], None, None)
    if status is None:
        try:
            page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_MS)
        except PlaywrightTimeoutError:
            pass  # pages that keep polling never go idle; "load" already fired
    final_url = page.url
    if state.blocked:
        emit("load", f"Blocked {len(state.blocked)} request(s) to unapproved origins")

    # ---- extract
    emit("extract", "Extracting interactive elements")
    findings, raw, stats = extract.extract_findings(page)
    emit("extract", f"Found {len(findings)} interactive elements")

    # ---- locators
    emit("locators", "Verifying locator candidates")
    verified = 0
    for finding, raw_element in zip(findings, raw, strict=True):
        if deadline.expired():
            break
        finding.locators = locators.verify(page, finding, raw_element.get("href"))
        verified += 1
    if verified < len(findings):
        status = status or InspectionStatus.timeout
        reasons.append(
            f"The job time limit was reached: locators were verified for {verified} of {len(findings)} Findings."
        )
    emit("locators", f"Verified locators for {verified} of {len(findings)} Findings")

    # ---- screenshot and crops
    emit("screenshot", "Taking full-page screenshot")
    screenshot: str | None = None
    try:
        page.screenshot(path=str(out_dir / "screenshot.png"), full_page=True)
        screenshot = "screenshot.png"
        take_crops(page, findings, out_dir, max_crops, deadline)
    except PlaywrightError:
        reasons.append("The screenshot could not be taken.")

    # ---- status
    login_detected, login_required = looks_like_login_wall(findings, url, final_url)
    if status is None and login_required:
        status = InspectionStatus.login_required
        reasons.append(
            "This page needs a login. Sign in by hand in the visible browser, then click Re-inspect. "
            "Credentials are never asked for or stored."
        )
    counts = count(findings)
    problems = []
    if counts.inaccessible:
        problems.append(f"{counts.inaccessible} element(s) are inaccessible (covered by another element or inert)")
    if stats["errors"]:
        problems.append(f"{stats['errors']} element(s) failed extraction")
    if stats["frames"]:
        problems.append(f"{stats['frames']} visible iframe(s) were not inspected")
    if problems:
        if status is None:
            status = InspectionStatus.partial
            inspected = counts.total - counts.inaccessible
            reasons.append(f"Inspected {inspected} of {counts.total} elements; " + "; ".join(problems) + ".")
        else:
            reasons.append("Also: " + "; ".join(problems) + ".")
    return result(findings, final_url, screenshot, login_detected)
