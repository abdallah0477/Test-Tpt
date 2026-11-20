"""The only code that reads or writes data/ (AD-2, AD-4, AD-5).

Paths are relative to the data root, e.g. "sessions/ses_.../session.json".
Four write modes, each atomic (temp file, fsync, rename/link) and locked per path:

    write_once(path, data)                 fails if the file exists
    update_json(path, fn, expected_rev)    increments `rev`; stale rev -> ConflictError (HTTP 409)
    append_jsonl(path, record)             appends one JSON line
    append_version(kind, id, content, ...) writes artifacts/{kind}/{id}/v{n}.json

Path owners (only writer) — keep this table in sync with the spine (AD-4):
    sessions/{ses}/session.json            v1/session         update_json
    sessions/{ses}/approvals.jsonl         utils/gates        append_jsonl
    sessions/{ses}/responses/{resp}.json   utils/agent_loop   write_once
    inspections/{ins}/inspection.json+blobs v1/inspection     write_once
    artifacts/{test_plan,test_code,repair}/{id}/v{n}.json     append_version
    runs/{run}/run.json + blobs            v1/execution       write_once
    runs/{run}/feedback.jsonl              v1/execution       append_jsonl
    usage/model_calls.jsonl                utils/model_client append_jsonl
The backend runs one uvicorn worker, so in-process locks are enough.
"""

import json
import os
import re
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from contracts import VersionEnvelope, VersionRef, content_sha256, utc_now
from pydantic import BaseModel

from app.utils.config import get_config

VERSION_KINDS = ("test_plan", "test_code", "repair")
_VERSION_FILE = re.compile(r"^v(\d+)\.json$")


class StoreError(Exception):
    """Base class for store errors."""


class AlreadyExistsError(StoreError):
    def __init__(self, path: str):
        super().__init__(f"{path} already exists")
        self.path = path


class ConflictError(StoreError):
    """update_json was given a stale rev. The API maps this to HTTP 409."""

    def __init__(self, path: str, expected_rev: int | None, current_rev: int):
        super().__init__(f"{path}: expected rev {expected_rev}, current rev is {current_rev}")
        self.path = path
        self.expected_rev = expected_rev
        self.current_rev = current_rev


class NotFoundError(StoreError):
    def __init__(self, path: str):
        super().__init__(f"{path} not found")
        self.path = path


# ---------------------------------------------------------------- paths and locks

_locks: dict[Path, threading.Lock] = {}
_locks_guard = threading.Lock()


def data_root() -> Path:
    return get_config().storage.data_dir


def resolve(path: str | Path) -> Path:
    """Absolute path under the data root; refuses anything that escapes it."""
    root = data_root().resolve()
    full = (root / path).resolve()
    if full != root and root not in full.parents:
        raise ValueError(f"path escapes the data root: {path}")
    return full


def _lock(full: Path) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(full, threading.Lock())


def _to_bytes(data: Any) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, BaseModel):
        return data.model_dump_json(indent=2).encode("utf-8")
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")


def _to_jsonable(data: Any) -> Any:
    return data.model_dump(mode="json") if isinstance(data, BaseModel) else data


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_temp(full: Path, payload: bytes) -> Path:
    """Write payload to a temp file next to `full` and fsync it."""
    full.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=full.parent, prefix=f".{full.name}.", suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    return Path(tmp)


def _replace(full: Path, payload: bytes) -> None:
    """Atomically replace (or create) `full`."""
    tmp = _write_temp(full, payload)
    os.replace(tmp, full)
    _fsync_dir(full.parent)


def _create_exclusive(full: Path, payload: bytes) -> bool:
    """Atomically create `full` only if it doesn't exist (link() fails like O_EXCL).

    Returns False if the file already exists. Readers never see a half-written file.
    """
    tmp = _write_temp(full, payload)
    try:
        os.link(tmp, full)
    except FileExistsError:
        return False
    finally:
        tmp.unlink()
    _fsync_dir(full.parent)
    return True


# ---------------------------------------------------------------- reads


def exists(path: str | Path) -> bool:
    return resolve(path).exists()


def read_bytes(path: str | Path) -> bytes:
    full = resolve(path)
    if not full.is_file():
        raise NotFoundError(str(path))
    return full.read_bytes()


def read_json(path: str | Path) -> Any:
    return json.loads(read_bytes(path))


def read_jsonl(path: str | Path) -> list[Any]:
    """All records of a JSONL file; a missing file is an empty list."""
    full = resolve(path)
    if not full.exists():
        return []
    return [json.loads(line) for line in full.read_text(encoding="utf-8").splitlines() if line.strip()]


def list_dir(path: str | Path) -> list[str]:
    full = resolve(path)
    return sorted(p.name for p in full.iterdir()) if full.is_dir() else []


# ---------------------------------------------------------------- write modes


def write_once(path: str | Path, data: Any) -> Path:
    """Create a file (JSON from a dict/model, or raw bytes). Raises AlreadyExistsError if it exists."""
    full = resolve(path)
    with _lock(full):
        if full.exists() or not _create_exclusive(full, _to_bytes(data)):
            raise AlreadyExistsError(str(path))
    return full


def update_json(path: str | Path, fn: Callable[[dict], dict], expected_rev: int | None) -> dict:
    """Read-modify-write a JSON object that carries a `rev` counter.

    `fn` gets the current object ({} if the file is missing) and returns the new one.
    If `expected_rev` is not None and differs from the stored rev (0 for a missing
    file), ConflictError is raised and nothing is written. Returns the stored object.
    """
    full = resolve(path)
    with _lock(full):
        current = json.loads(full.read_bytes()) if full.exists() else {}
        current_rev = int(current.get("rev", 0))
        if expected_rev is not None and expected_rev != current_rev:
            raise ConflictError(str(path), expected_rev, current_rev)
        updated = _to_jsonable(fn(dict(current)))
        updated["rev"] = current_rev + 1
        _replace(full, _to_bytes(updated))
    return updated


def append_jsonl(path: str | Path, record: Any) -> None:
    """Append one record as a single JSON line.

    The file is rewritten to a temp file and renamed, so a crash never leaves a
    half-written line; the per-path lock keeps concurrent appends from interleaving.
    """
    full = resolve(path)
    line = json.dumps(_to_jsonable(record), ensure_ascii=False, separators=(",", ":")) + "\n"
    with _lock(full):
        existing = full.read_bytes() if full.exists() else b""
        if existing and not existing.endswith(b"\n"):
            existing += b"\n"
        _replace(full, existing + line.encode("utf-8"))


def _version_numbers(directory: Path) -> list[int]:
    if not directory.is_dir():
        return []
    return sorted(int(m.group(1)) for p in directory.iterdir() if (m := _VERSION_FILE.match(p.name)))


def append_version(
    kind: str,
    id: str,
    content: Any,
    *,
    session_id: str,
    created_by: str,
    derived_from: list[VersionRef] | None = None,
    restored_from: int | None = None,
) -> VersionEnvelope:
    """Write the next version of an artifact (AD-5).

    The store alone assigns `version` (n+1, under the lock, exclusive create) and
    computes `content_sha256` from the canonical JSON of `content` only.
    """
    if kind not in VERSION_KINDS:
        raise ValueError(f"unknown artifact kind: {kind!r}")
    content = _to_jsonable(content)
    directory = resolve(f"artifacts/{kind}/{id}")
    with _lock(directory):
        n = (_version_numbers(directory) or [0])[-1] + 1
        while True:
            envelope = VersionEnvelope(
                kind=kind,
                id=id,
                version=n,
                session_id=session_id,
                created_at=utc_now(),
                created_by=created_by,
                derived_from=derived_from or [],
                restored_from=restored_from,
                content_sha256=content_sha256(content),
                content=content,
            )
            if _create_exclusive(directory / f"v{n}.json", _to_bytes(envelope)):
                return envelope
            n += 1  # someone outside this process wrote vN; never overwrite it


def read_version(kind: str, id: str, version: int | None = None) -> VersionEnvelope:
    """Read one version, or the latest when `version` is None."""
    if version is None:
        numbers = _version_numbers(resolve(f"artifacts/{kind}/{id}"))
        if not numbers:
            raise NotFoundError(f"artifacts/{kind}/{id}")
        version = numbers[-1]
    return VersionEnvelope.model_validate(read_json(f"artifacts/{kind}/{id}/v{version}.json"))


def list_versions(kind: str, id: str) -> list[int]:
    return _version_numbers(resolve(f"artifacts/{kind}/{id}"))
