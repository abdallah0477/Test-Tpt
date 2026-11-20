"""Approval gates: the only code that reads or writes approvals (AD-2, AD-6, AD-15).

record(gate, session_id, origin=... | target=..., content_sha256=...)  -> Approval
require(action, session_id, ...)   raises GateError unless the preconditions hold
approved_origins(session_id)       G0 origins, the only allow-list for the Runner
"""

from collections.abc import Callable
from urllib.parse import urlsplit

from contracts import Approval, Gate, OriginTarget, VersionRef

from app.utils import store


class GateError(Exception):
    """A gated action's preconditions are not met. The API maps this to HTTP 403."""

    def __init__(self, action: str, message: str):
        super().__init__(f"{action}: {message}")
        self.action = action
        self.message = message


class GateNotImplementedError(GateError):
    """The action belongs to Phase 2; it fails closed until it is built."""


def _approvals_path(session_id: str) -> str:
    return f"sessions/{session_id}/approvals.jsonl"


def origin_of(url: str) -> str:
    """Normalized origin `scheme://host[:port]`; default ports are dropped."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not an http(s) URL: {url!r}")
    host = parts.hostname.lower()
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    port = parts.port
    if port is None or (scheme, port) in (("http", 80), ("https", 443)):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def record(
    gate: Gate | str,
    session_id: str,
    *,
    origin: str | None = None,
    target: VersionRef | None = None,
    content_sha256: str | None = None,
) -> Approval:
    """Append an Approval to sessions/{ses}/approvals.jsonl.

    G0 takes an `origin` (a URL or origin; it is normalized). Other gates take a
    version `target` and its `content_sha256`.
    """
    gate = Gate(gate)
    if gate is Gate.G0:
        if origin is None or target is not None:
            raise ValueError("G0 needs an origin and no version target")
        approval = Approval(gate=gate, session_id=session_id, target=OriginTarget(origin=origin_of(origin)))
    else:
        if target is None:
            raise ValueError(f"{gate} needs a version target")
        approval = Approval(gate=gate, session_id=session_id, target=target, content_sha256=content_sha256)
    store.append_jsonl(_approvals_path(session_id), approval)
    return approval


def approvals(session_id: str) -> list[Approval]:
    return [Approval.model_validate(line) for line in store.read_jsonl(_approvals_path(session_id))]


def approved_origins(session_id: str) -> list[str]:
    """Distinct G0 origins of a Session, in approval order."""
    origins: list[str] = []
    for approval in approvals(session_id):
        if approval.gate is Gate.G0 and isinstance(approval.target, OriginTarget):
            if approval.target.origin not in origins:
                origins.append(approval.target.origin)
    return origins


# ---------------------------------------------------------------- preconditions (AD-6)


def _require_load_url(session_id: str, url: str) -> None:
    try:
        origin = origin_of(url)
    except ValueError as exc:
        raise GateError("runner.load_url", str(exc)) from exc
    if origin not in approved_origins(session_id):
        raise GateError("runner.load_url", f"origin {origin} has no G0 approval in this session")


def _phase2(action: str, preconditions: str) -> Callable[..., None]:
    def check(*_args, **_kwargs) -> None:
        raise GateNotImplementedError(action, f"not available yet (needs: {preconditions})")

    return check


REQUIREMENTS: dict[str, Callable[..., None]] = {
    "runner.load_url": _require_load_url,
    "codegen.generate": _phase2(
        "codegen.generate", "G1 on that test_plan version, no expected result left as assumption"
    ),
    "execution.run": _phase2(
        "execution.run", "validation passed + G2 + G3 on that test_code version + G0 for every origin"
    ),
    "execution.rerun": _phase2("execution.rerun", "G4 for this rerun"),
    "maintenance.apply": _phase2("maintenance.apply", "G5 on that repair version"),
}


def require(action: str, session_id: str, *args, **kwargs) -> None:
    """Raise GateError unless `action` is allowed now.

    Example: require("runner.load_url", session_id, url)
    """
    check = REQUIREMENTS.get(action)
    if check is None:
        raise GateError(action, "unknown gated action")
    check(session_id, *args, **kwargs)
